import re
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from app.db.collections import (
    get_patients_collection,
    get_ehr_records_collection,
    get_sessions_collection,
    get_messages_collection,
    get_users_collection,
    get_gridfs
)

logger = logging.getLogger(__name__)

# ==============================================================================
# User Repository
# ==============================================================================

def get_user(patient_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user document by patient_id."""
    col = get_users_collection()
    return col.find_one({"patient_id": patient_id})

def upsert_user(user_data: Dict[str, Any]) -> str:
    """
    Inserts or updates a user document idempotently.
    Requires 'patient_id' in user_data.
    """
    col = get_users_collection()
    patient_id = user_data.get("patient_id")
    if not patient_id:
        raise ValueError("User data must contain 'patient_id'")

    if "_id" not in user_data:
        user_data["_id"] = patient_id

    if "created_at" not in user_data:
        user_data["created_at"] = datetime.now(timezone.utc)

    col.replace_one({"patient_id": patient_id}, user_data, upsert=True)
    return patient_id


# ==============================================================================
# Patient Repository
# ==============================================================================

def get_patient(patient_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single patient document by its ID (e.g. 'P001')."""
    col = get_patients_collection()
    return col.find_one({"_id": patient_id})

def get_all_patient_ids() -> List[str]:
    """Retrieves sorted list of all patient IDs in the database."""
    col = get_patients_collection()
    docs = col.find({}, {"_id": 1}).sort("_id", ASCENDING)
    return [doc["_id"] for doc in docs]

def get_all_patients() -> List[Dict[str, Any]]:
    """Retrieves all patient documents sorted by ID."""
    col = get_patients_collection()
    return list(col.find({}).sort("_id", ASCENDING))

def generate_next_patient_id() -> str:
    """
    Generates the next available patient ID (e.g. 'P031') by inspecting existing IDs.
    Guarantees no collisions.
    """
    col = get_patients_collection()
    docs = col.find({}, {"_id": 1})
    max_num = 0
    for doc in docs:
        pid = doc.get("_id", "")
        match = re.match(r"^P(\d+)$", pid, re.IGNORECASE)
        if match:
            max_num = max(max_num, int(match.group(1)))
    next_num = max_num + 1 if max_num > 0 else 1
    return f"P{next_num:03d}"

def get_all_patients_with_metadata() -> List[Dict[str, Any]]:
    """
    Retrieves all patients augmented with account status (is_active) and EHR record count.
    Used by the Admin Dashboard.
    """
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    ehr_col = get_ehr_records_collection()

    patients = list(patients_col.find({}).sort("_id", ASCENDING))
    users = {u["patient_id"]: u for u in users_col.find({})}

    # Aggregate record counts by patient_id
    pipeline = [
        {"$group": {"_id": "$patient_id", "count": {"$sum": 1}}}
    ]
    counts_map = {item["_id"]: item["count"] for item in ehr_col.aggregate(pipeline)}

    results = []
    for p in patients:
        pid = p["_id"]
        user_info = users.get(pid, {})
        results.append({
            "patient_id": pid,
            "name": p.get("name", f"Patient {pid}"),
            "age": p.get("age"),
            "gender": p.get("gender"),
            "is_active": user_info.get("is_active", True),
            "record_count": counts_map.get(pid, 0),
            "created_at": p.get("created_at")
        })
    return results

def upsert_patient(patient_data: Dict[str, Any]) -> str:
    """
    Inserts or updates a patient document idempotently.
    Requires '_id' in patient_data.
    """
    col = get_patients_collection()
    patient_id = patient_data.get("_id")
    if not patient_id:
        raise ValueError("Patient data must contain '_id'")

    if "created_at" not in patient_data:
        patient_data["created_at"] = datetime.now(timezone.utc)

    col.replace_one({"_id": patient_id}, patient_data, upsert=True)
    return patient_id

def update_patient_demographics(patient_id: str, update_fields: Dict[str, Any]) -> bool:
    """Updates demographic fields (name, age, gender) for a patient."""
    col = get_patients_collection()
    allowed = {k: v for k, v in update_fields.items() if k in ["name", "age", "gender"] and v is not None}
    if not allowed:
        return False
    res = col.update_one({"_id": patient_id}, {"$set": allowed})
    return res.matched_count > 0

def set_patient_active_status(patient_id: str, is_active: bool) -> bool:
    """
    Activates or deactivates a patient account in the users collection.
    Preserves all patient data, EHR records, sessions, and audio.
    """
    users_col = get_users_collection()
    now = datetime.now(timezone.utc)
    res = users_col.update_one(
        {"patient_id": patient_id},
        {"$set": {"is_active": is_active, "updated_at": now}}
    )
    return res.matched_count > 0

def delete_patient_cascade(patient_id: str) -> bool:
    """
    Destructive permanent removal of patient profile, user credentials,
    all EHR records, chat sessions, messages, and referenced voice recordings.
    """
    # 1. Clean up sessions, messages, and audio
    sessions = get_sessions_by_patient(patient_id)
    for s in sessions:
        delete_messages_for_patient_session(s["_id"], patient_id)
        delete_session_for_patient(s["_id"], patient_id)

    # 2. Clean up all EHR records
    ehr_col = get_ehr_records_collection()
    ehr_col.delete_many({"patient_id": patient_id})

    # 3. Clean up user
    users_col = get_users_collection()
    users_col.delete_one({"patient_id": patient_id})

    # 4. Clean up patient profile
    patients_col = get_patients_collection()
    res = patients_col.delete_one({"_id": patient_id})
    return res.deleted_count > 0


# ==============================================================================
# EHR Record Repository (1 Patient -> Many EHR Records)
# ==============================================================================

def generate_next_ehr_id(patient_id: str) -> str:
    """
    Generates the next monotonic sequence EHR record ID (e.g. 'ehr_P001_004').
    
    GUARANTEES:
    - Strictly monotonic sequence number.
    - Sequences are NEVER reused even if intermediate records are deleted.
    - Inspects both patient.last_ehr_seq and any existing records to ensure forward progression.
    """
    patients_col = get_patients_collection()
    ehr_col = get_ehr_records_collection()

    patient_doc = patients_col.find_one({"_id": patient_id})
    stored_seq = patient_doc.get("last_ehr_seq", 0) if patient_doc else 0

    # Scan existing records for patient to check current highest suffix
    existing_records = ehr_col.find({"patient_id": patient_id}, {"_id": 1, "chunk_id": 1})
    max_present = 0
    pattern = re.compile(rf"^ehr_{re.escape(patient_id)}_(\d+)$", re.IGNORECASE)
    for rec in existing_records:
        rec_id = rec.get("_id", "")
        match = pattern.match(rec_id)
        if match:
            max_present = max(max_present, int(match.group(1)))

    next_seq = max(stored_seq, max_present) + 1

    # Persist the incremented monotonic sequence to the patient record
    patients_col.update_one(
        {"_id": patient_id},
        {"$set": {"last_ehr_seq": next_seq}},
        upsert=False
    )

    return f"ehr_{patient_id}_{next_seq:03d}"

def get_ehr_records_by_patient(patient_id: str, sort_newest_first: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieves all EHR clinical records belonging strictly to a patient_id.
    Guarantees deterministic, patient-isolated record retrieval.
    Sorts chronologically (by recorded_at or created_at).
    """
    col = get_ehr_records_collection()
    sort_dir = DESCENDING if sort_newest_first else ASCENDING
    return list(col.find({"patient_id": patient_id}).sort([("recorded_at", sort_dir), ("created_at", sort_dir)]))

def get_ehr_record_by_id(record_id: str, patient_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a single EHR record by ID, optionally validating patient ownership."""
    col = get_ehr_records_collection()
    query: Dict[str, Any] = {"_id": record_id}
    if patient_id:
        query["patient_id"] = patient_id
    return col.find_one(query)

def create_ehr_record(
    patient_id: str,
    content: str,
    chunk_type: str = "clinical_note",
    recorded_at: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Creates a new medical record document for a patient with auto-generated sequence ID.
    Enforces monotonic ID allocation (no reuse).
    Separates recorded_at (event time), created_at (entry time), and updated_at (modification time).
    """
    col = get_ehr_records_collection()
    record_id = generate_next_ehr_id(patient_id)
    now = datetime.now(timezone.utc)
    rec_time = recorded_at if recorded_at is not None else now

    doc = {
        "_id": record_id,
        "patient_id": patient_id,
        "chunk_id": record_id,
        "chunk_type": chunk_type or "clinical_note",
        "content": content.strip(),
        "metadata": metadata or {
            "source": "EHR",
            "source_type": "ehr"
        },
        "recorded_at": rec_time,
        "created_at": now,
        "updated_at": now
    }
    col.insert_one(doc)
    logger.info(f"Created new EHR record '{record_id}' for patient '{patient_id}'.")
    return doc

def update_ehr_record(
    record_id: str,
    patient_id: str,
    content: Optional[str] = None,
    chunk_type: Optional[str] = None,
    recorded_at: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Updates an existing EHR record. Updates updated_at timestamp.
    Enforces patient ownership verification.
    """
    col = get_ehr_records_collection()
    now = datetime.now(timezone.utc)
    updates: Dict[str, Any] = {"updated_at": now}

    if content is not None:
        updates["content"] = content.strip()
    if chunk_type is not None:
        updates["chunk_type"] = chunk_type
    if recorded_at is not None:
        updates["recorded_at"] = recorded_at

    res = col.find_one_and_update(
        {"_id": record_id, "patient_id": patient_id},
        {"$set": updates},
        return_document=True
    )
    return res

def delete_ehr_record(record_id: str, patient_id: Optional[str] = None) -> bool:
    """
    Deletes a specific medical record document from ehr_records.
    Sequence numbers are never reused upon deletion.
    """
    col = get_ehr_records_collection()
    query: Dict[str, Any] = {"_id": record_id}
    if patient_id:
        query["patient_id"] = patient_id
    res = col.delete_one(query)
    return res.deleted_count > 0

def upsert_ehr_record(record_data: Dict[str, Any]) -> str:
    """
    Inserts or updates an EHR record document idempotently.
    Ensures recorded_at, created_at, updated_at are properly set.
    """
    col = get_ehr_records_collection()
    record_id = record_data.get("_id")
    patient_id = record_data.get("patient_id")
    chunk_id = record_data.get("chunk_id")

    if not record_id:
        if patient_id and chunk_id:
            record_id = f"{chunk_id}"
            record_data["_id"] = record_id
        else:
            record_id = f"ehr_{uuid.uuid4().hex[:8]}"
            record_data["_id"] = record_id

    now = datetime.now(timezone.utc)
    if "created_at" not in record_data:
        record_data["created_at"] = now
    if "recorded_at" not in record_data:
        record_data["recorded_at"] = record_data["created_at"]
    if "updated_at" not in record_data:
        record_data["updated_at"] = now

    col.replace_one({"_id": record_id}, record_data, upsert=True)
    return record_id


# ==============================================================================
# Session Repository
# ==============================================================================

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a session document by session_id."""
    col = get_sessions_collection()
    return col.find_one({"_id": session_id})

def get_session_for_patient(session_id: str, patient_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a session document strictly verifying patient ownership."""
    col = get_sessions_collection()
    return col.find_one({"_id": session_id, "patient_id": patient_id})

def get_sessions_by_patient(patient_id: str) -> List[Dict[str, Any]]:
    """Retrieves all sessions belonging to a specific patient, ordered newest first."""
    col = get_sessions_collection()
    return list(col.find({"patient_id": patient_id}).sort("updated_at", DESCENDING))

def create_session(session_id: str, patient_id: str, title: Optional[str] = None, status: str = "active") -> Dict[str, Any]:
    """Creates a new session document bound to a specific patient_id with an optional title."""
    col = get_sessions_collection()
    now = datetime.now(timezone.utc)
    session_doc = {
        "_id": session_id,
        "patient_id": patient_id,
        "title": title or "New Conversation",
        "created_at": now,
        "updated_at": now,
        "status": status
    }
    col.replace_one({"_id": session_id}, session_doc, upsert=True)
    return session_doc

def update_session_timestamp(session_id: str) -> bool:
    """Updates the updated_at timestamp of a session."""
    col = get_sessions_collection()
    now = datetime.now(timezone.utc)
    res = col.update_one({"_id": session_id}, {"$set": {"updated_at": now}})
    return res.matched_count > 0

def update_session_title(session_id: str, title: str) -> bool:
    """Updates the title and updated_at timestamp of a session."""
    col = get_sessions_collection()
    now = datetime.now(timezone.utc)
    res = col.update_one({"_id": session_id}, {"$set": {"title": title, "updated_at": now}})
    return res.matched_count > 0

def delete_session(session_id: str) -> bool:
    """Deletes a session document by session_id."""
    col = get_sessions_collection()
    res = col.delete_one({"_id": session_id})
    return res.deleted_count > 0

def delete_session_for_patient(session_id: str, patient_id: str) -> bool:
    """Deletes a session document strictly verifying patient ownership."""
    col = get_sessions_collection()
    res = col.delete_one({"_id": session_id, "patient_id": patient_id})
    return res.deleted_count > 0


# ==============================================================================
# GridFS Audio Storage Repository
# ==============================================================================

def save_audio_file(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    patient_id: str,
    session_id: str,
    message_id: Optional[str] = None
) -> str:
    """
    Persists original voice recording binary to MongoDB GridFS.
    Stores metadata including patient_id, session_id, and mime content_type.
    Returns string representation of the GridFS file ObjectId.
    """
    fs = get_gridfs()
    file_id = fs.put(
        audio_bytes,
        filename=filename,
        content_type=content_type,
        metadata={
            "patient_id": patient_id,
            "session_id": session_id,
            "message_id": message_id,
            "content_type": content_type,
            "created_at": datetime.now(timezone.utc),
            "size_bytes": len(audio_bytes)
        }
    )
    return str(file_id)

def get_audio_file(file_id: str):
    """
    Retrieves a GridFS file by its string ObjectId.
    Returns GridOut object or None if not found/invalid ID.
    """
    fs = get_gridfs()
    try:
        oid = ObjectId(file_id)
        return fs.get(oid)
    except Exception as e:
        logger.warning(f"Failed to retrieve GridFS file '{file_id}': {e}")
        return None

def delete_audio_file(file_id: str) -> bool:
    """
    Deletes a GridFS file by its string ObjectId.
    """
    fs = get_gridfs()
    try:
        oid = ObjectId(file_id)
        fs.delete(oid)
        return True
    except Exception as e:
        logger.warning(f"Failed to delete GridFS file '{file_id}': {e}")
        return False


# ==============================================================================
# Message Repository
# ==============================================================================

def save_message(
    session_id: str,
    patient_id: str,
    role: str,
    content: str,
    sources: Optional[List[str]] = None,
    message_id: Optional[str] = None,
    input_type: str = "text",
    audio_file_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves a single chat message (user or assistant) associated with a session_id and patient_id.
    Retains input_type ('text' | 'voice') and GridFS audio_file_id for voice messages.
    """
    col = get_messages_collection()
    now = datetime.now(timezone.utc)
    doc = {
        "_id": message_id or f"msg_{uuid.uuid4().hex}",
        "session_id": session_id,
        "patient_id": patient_id,
        "role": role,
        "content": content,
        "input_type": input_type,
        "audio_file_id": audio_file_id,
        "timestamp": now,
        "sources": sources if sources is not None else []
    }
    col.insert_one(doc)
    return doc

def get_message(message_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single message by its ID."""
    col = get_messages_collection()
    return col.find_one({"_id": message_id})

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """Retrieves all messages for a given session sorted chronologically (ascending)."""
    col = get_messages_collection()
    return list(col.find({"session_id": session_id}).sort("timestamp", ASCENDING))

def get_session_messages_for_patient(session_id: str, patient_id: str) -> List[Dict[str, Any]]:
    """Retrieves all messages for a given session strictly bound to the authenticated patient_id."""
    col = get_messages_collection()
    return list(col.find({"session_id": session_id, "patient_id": patient_id}).sort("timestamp", ASCENDING))

def delete_messages_by_session(session_id: str) -> int:
    """Deletes all messages associated with a session_id and cleans up referenced GridFS audio."""
    col = get_messages_collection()
    # Find and delete any linked GridFS files
    try:
        voice_msgs = col.find({"session_id": session_id, "audio_file_id": {"$ne": None}})
        for m in voice_msgs:
            if m.get("audio_file_id"):
                delete_audio_file(m["audio_file_id"])
    except Exception as e:
        logger.warning(f"Error cleaning up GridFS files for session '{session_id}': {e}")

    res = col.delete_many({"session_id": session_id})
    return res.deleted_count

def delete_messages_for_patient_session(session_id: str, patient_id: str) -> int:
    """Deletes all messages for a session belonging to a specific patient and cleans up GridFS audio."""
    col = get_messages_collection()
    try:
        voice_msgs = col.find({"session_id": session_id, "patient_id": patient_id, "audio_file_id": {"$ne": None}})
        for m in voice_msgs:
            if m.get("audio_file_id"):
                delete_audio_file(m["audio_file_id"])
    except Exception as e:
        logger.warning(f"Error cleaning up GridFS files for patient '{patient_id}' session '{session_id}': {e}")

    res = col.delete_many({"session_id": session_id, "patient_id": patient_id})
    return res.deleted_count


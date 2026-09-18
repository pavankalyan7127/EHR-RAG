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


# ==============================================================================
# EHR Record Repository
# ==============================================================================

def get_ehr_records_by_patient(patient_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves all EHR clinical note chunks belonging strictly to a patient_id.
    Guarantees deterministic, patient-isolated record retrieval.
    """
    col = get_ehr_records_collection()
    return list(col.find({"patient_id": patient_id}).sort("created_at", ASCENDING))

def upsert_ehr_record(record_data: Dict[str, Any]) -> str:
    """
    Inserts or updates an EHR record document idempotently.
    Requires '_id' or ('patient_id' and 'chunk_id').
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

    if "created_at" not in record_data:
        record_data["created_at"] = datetime.now(timezone.utc)

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


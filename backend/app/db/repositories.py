import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pymongo import ASCENDING
from app.db.collections import (
    get_patients_collection,
    get_ehr_records_collection,
    get_sessions_collection,
    get_messages_collection
)

logger = logging.getLogger(__name__)

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

def create_session(session_id: str, patient_id: str, status: str = "active") -> Dict[str, Any]:
    """Creates a new session document bound to a specific patient_id."""
    col = get_sessions_collection()
    now = datetime.now(timezone.utc)
    session_doc = {
        "_id": session_id,
        "patient_id": patient_id,
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

def delete_session(session_id: str) -> bool:
    """Deletes a session document by session_id."""
    col = get_sessions_collection()
    res = col.delete_one({"_id": session_id})
    return res.deleted_count > 0


# ==============================================================================
# Message Repository
# ==============================================================================

def save_message(
    session_id: str,
    patient_id: str,
    role: str,
    content: str,
    sources: Optional[List[str]] = None,
    message_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves a single chat message (user or assistant) associated with a session_id and patient_id.
    Stores source chunk provenance for assistant messages.
    """
    col = get_messages_collection()
    now = datetime.now(timezone.utc)
    doc = {
        "_id": message_id or f"msg_{uuid.uuid4().hex}",
        "session_id": session_id,
        "patient_id": patient_id,
        "role": role,
        "content": content,
        "timestamp": now,
        "sources": sources if sources is not None else []
    }
    col.insert_one(doc)
    return doc

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """Retrieves all messages for a given session sorted chronologically (ascending)."""
    col = get_messages_collection()
    return list(col.find({"session_id": session_id}).sort("timestamp", ASCENDING))

def delete_messages_by_session(session_id: str) -> int:
    """Deletes all messages associated with a session_id."""
    col = get_messages_collection()
    res = col.delete_many({"session_id": session_id})
    return res.deleted_count

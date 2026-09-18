import logging
from typing import List, Optional
from app.models.schemas import ChatMessage
from app.db.repositories import (
    get_session,
    create_session,
    update_session_timestamp,
    delete_session,
    save_message,
    get_session_messages,
    delete_messages_by_session
)

logger = logging.getLogger(__name__)

class PatientSessionMismatchError(Exception):
    """Raised when an existing session is accessed with a different patient ID."""
    pass

def get_or_create_session(session_id: str, patient_id: str) -> dict:
    """
    Verifies that the session exists and belongs to the specified patient_id.
    If the session does not exist, creates it for patient_id.
    If the session exists for a different patient, raises PatientSessionMismatchError.
    """
    existing_session = get_session(session_id)
    if existing_session:
        assigned_patient = existing_session.get("patient_id")
        if assigned_patient != patient_id:
            logger.warning(
                f"Session security violation: Session '{session_id}' belongs to patient '{assigned_patient}', "
                f"but was requested for patient '{patient_id}'."
            )
            raise PatientSessionMismatchError(
                f"Session '{session_id}' is already assigned to patient '{assigned_patient}' and cannot be used with '{patient_id}'."
            )
        return existing_session

    # Create new session
    logger.info(f"Creating new session '{session_id}' for patient '{patient_id}'.")
    return create_session(session_id, patient_id)

def get_session_history(session_id: str) -> List[ChatMessage]:
    """
    Retrieves chronological conversation history for a specific session ID from MongoDB.
    Maps Message documents to ChatMessage schemas.
    """
    messages = get_session_messages(session_id)
    history: List[ChatMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ["user", "assistant"] and content:
            history.append(ChatMessage(role=role, content=content))
    return history

def add_turn_to_session(
    session_id: str,
    patient_id: str,
    user_message: str,
    assistant_message: str,
    sources: Optional[List[str]] = None
) -> List[ChatMessage]:
    """
    Persists a multi-turn user/assistant interaction and provenance into MongoDB,
    updates session timestamp, and returns the full updated history.
    """
    # 1. Save user message
    save_message(
        session_id=session_id,
        patient_id=patient_id,
        role="user",
        content=user_message,
        sources=[]
    )

    # 2. Save assistant response with source provenance
    save_message(
        session_id=session_id,
        patient_id=patient_id,
        role="assistant",
        content=assistant_message,
        sources=sources or []
    )

    # 3. Update session updated_at
    update_session_timestamp(session_id)

    # 4. Return complete chronological history
    return get_session_history(session_id)

def clear_session_history(session_id: str) -> bool:
    """
    Clears all messages and removes the session from MongoDB.
    """
    deleted_messages_count = delete_messages_by_session(session_id)
    deleted_session = delete_session(session_id)
    return deleted_messages_count > 0 or deleted_session

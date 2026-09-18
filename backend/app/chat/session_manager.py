import logging
from typing import List, Optional
from app.models.schemas import ChatMessage
from app.db.repositories import (
    get_session,
    get_session_for_patient,
    create_session,
    update_session_timestamp,
    update_session_title,
    delete_session,
    delete_session_for_patient,
    save_message,
    get_session_messages,
    get_session_messages_for_patient,
    delete_messages_by_session,
    delete_messages_for_patient_session
)

logger = logging.getLogger(__name__)

class PatientSessionMismatchError(Exception):
    """Raised when an existing session is accessed with a different patient ID."""
    pass


def generate_local_title(text: str, max_length: int = 42) -> str:
    """
    Derives a concise, clean session title locally from the first user query.
    Avoids expensive LLM generation overhead.
    """
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return "New Conversation"
    if len(cleaned) <= max_length:
        return cleaned
    truncated = cleaned[:max_length].rsplit(" ", 1)[0]
    return (truncated or cleaned[:max_length]).strip() + "..."


def get_or_create_session(session_id: str, patient_id: str, title: Optional[str] = None) -> dict:
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
    return create_session(session_id, patient_id, title=title)


def get_session_history(session_id: str) -> List[ChatMessage]:
    """
    Retrieves complete chronological conversation history for a specific session ID from MongoDB.
    Maps Message documents to ChatMessage schemas with audio metadata if present.
    """
    messages = get_session_messages(session_id)
    history: List[ChatMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ["user", "assistant"] and content:
            msg_id = str(msg.get("_id", ""))
            input_type = msg.get("input_type", "text")
            audio_file_id = msg.get("audio_file_id")
            audio_url = f"/chat/messages/{msg_id}/audio" if audio_file_id else None

            history.append(ChatMessage(
                id=msg_id,
                role=role,
                content=content,
                input_type=input_type,
                audio_file_id=audio_file_id,
                audio_url=audio_url,
                timestamp=msg.get("timestamp"),
                sources=msg.get("sources", [])
            ))
    return history


def get_patient_session_history(session_id: str, patient_id: str) -> List[ChatMessage]:
    """
    Retrieves complete chronological conversation history strictly bound to the authenticated patient.
    Populates input_type, audio_file_id, and audio_url for voice messages.
    """
    messages = get_session_messages_for_patient(session_id, patient_id)
    history: List[ChatMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ["user", "assistant"] and content:
            msg_id = str(msg.get("_id", ""))
            input_type = msg.get("input_type", "text")
            audio_file_id = msg.get("audio_file_id")
            audio_url = f"/chat/messages/{msg_id}/audio" if audio_file_id else None

            history.append(ChatMessage(
                id=msg_id,
                role=role,
                content=content,
                input_type=input_type,
                audio_file_id=audio_file_id,
                audio_url=audio_url,
                timestamp=msg.get("timestamp"),
                sources=msg.get("sources", [])
            ))
    return history


def get_recent_history_window(history: List[ChatMessage], window_size: Optional[int] = 6) -> List[ChatMessage]:
    """
    Extracts the most recent `window_size` messages from the chronological history for LLM prompt context.
    If window_size is None or <= 0 or greater than total messages, returns all messages.
    Does NOT mutate or delete messages from the database.
    """
    if not history or window_size is None or window_size <= 0 or len(history) <= window_size:
        return list(history)
    return history[-window_size:]


def add_turn_to_session(
    session_id: str,
    patient_id: str,
    user_message: str,
    assistant_message: str,
    sources: Optional[List[str]] = None,
    input_type: str = "text",
    audio_file_id: Optional[str] = None
) -> List[ChatMessage]:
    """
    Persists a multi-turn user/assistant interaction and provenance into MongoDB,
    auto-generates title if needed, stores input_type and audio_file_id for voice recordings,
    updates session timestamp, and returns the full updated history.
    """
    # 1. Check if session needs a meaningful title (if currently default)
    session_doc = get_session(session_id)
    if session_doc:
        current_title = session_doc.get("title", "")
        if not current_title or current_title == "New Conversation":
            new_title = generate_local_title(user_message)
            update_session_title(session_id, new_title)

    # 2. Save user message (with voice metadata if recorded)
    save_message(
        session_id=session_id,
        patient_id=patient_id,
        role="user",
        content=user_message,
        sources=[],
        input_type=input_type,
        audio_file_id=audio_file_id
    )

    # 3. Save assistant response with source provenance
    save_message(
        session_id=session_id,
        patient_id=patient_id,
        role="assistant",
        content=assistant_message,
        sources=sources or [],
        input_type="text",
        audio_file_id=None
    )

    # 4. Update session updated_at
    update_session_timestamp(session_id)

    # 5. Return complete chronological history
    return get_patient_session_history(session_id, patient_id)


def clear_session_history(session_id: str) -> bool:
    """
    Clears all messages and removes the session from MongoDB.
    """
    deleted_messages_count = delete_messages_by_session(session_id)
    deleted_session = delete_session(session_id)
    return deleted_messages_count > 0 or deleted_session


def clear_session_for_patient(session_id: str, patient_id: str) -> bool:
    """
    Clears all messages and removes the session strictly verifying patient ownership.
    """
    deleted_messages_count = delete_messages_for_patient_session(session_id, patient_id)
    deleted_session = delete_session_for_patient(session_id, patient_id)
    return deleted_messages_count > 0 or deleted_session

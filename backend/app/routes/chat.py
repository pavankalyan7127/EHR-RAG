import io
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DeleteSessionResponse,
    SessionSummary,
    SessionDetailResponse,
    CreateSessionRequest
)
from app.db.repositories import (
    get_patient,
    get_session,
    get_session_for_patient,
    get_sessions_by_patient,
    create_session,
    get_message,
    get_audio_file
)
from app.core.auth import get_current_patient, get_current_patient_flexible, AuthenticatedPatient
from app.core.retrieval import retrieve_context, build_context_block
from app.core.generation import generate_answer, GeminiQuotaExhaustedError
from app.chat.session_manager import (
    get_or_create_session,
    get_patient_session_history,
    add_turn_to_session,
    clear_session_for_patient,
    PatientSessionMismatchError
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Chat"])


async def process_chat_query(
    session_id: str,
    patient_id: str,
    message_text: str,
    input_type: str = "text",
    audio_file_id: Optional[str] = None
) -> ChatResponse:
    """
    Core RAG pipeline orchestration:
    1. Validates patient exists in MongoDB.
    2. Validates/creates session with patient ownership check.
    3. Retrieves patient EHR from MongoDB with local semantic relevance selection + external MedQuAD from FAISS.
    4. Fetches multi-turn history from MongoDB.
    5. Builds grounded context and generates response via Gemini (with prompt history windowing & monitoring).
    6. Persists conversation turn with source provenance and auto-title to MongoDB.
    7. Returns complete updated conversation history in response.
    """
    cleaned_message = message_text.strip()
    if not cleaned_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty."
        )

    # 1. Validate Patient Existence in MongoDB
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID '{patient_id}' not found in EHR database."
        )

    # 2. Validate/Create Session and Enforce Patient Ownership
    try:
        get_or_create_session(session_id, patient_id)
    except PatientSessionMismatchError as pe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(pe)
        )

    # 3. Dual-Track Retrieval: Patient EHR from MongoDB + MedQuAD from FAISS
    patient_records, external_records = retrieve_context(
        patient_id=patient_id,
        query=cleaned_message,
        top_k_external=3
    )

    # 4. Context Assembly & History Retrieval (Full history retrieved from DB for patient)
    context_block = build_context_block(patient_id, patient_records, external_records)
    history = get_patient_session_history(session_id, patient_id)

    # 5. Grounded Generation via Gemini
    try:
        answer = generate_answer(
            context_block=context_block,
            history=history,
            message=cleaned_message,
            patient_chunks_count=len(patient_records),
            external_chunks_count=len(external_records)
        )
    except GeminiQuotaExhaustedError as qe:
        logger.error(f"Gemini API quota depletion: {str(qe)}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Gemini API quota or prepaid credits have been exhausted. Please verify billing and quota limits."
        )
    except Exception as e:
        logger.error(f"Generation failure: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}"
        )

    # 6. Source Provenance Tracking
    patient_sources = [
        rec.get("chunk_id") or rec.get("_id") for rec in patient_records
        if rec.get("chunk_id") or rec.get("_id")
    ]
    external_sources = [
        chunk.get("chunk_id") for chunk in external_records
        if chunk.get("chunk_id")
    ]
    all_sources = patient_sources + external_sources

    # 7. Persist Turn to MongoDB (User + Assistant Messages + Auto Title)
    updated_history = add_turn_to_session(
        session_id=session_id,
        patient_id=patient_id,
        user_message=cleaned_message,
        assistant_message=answer,
        sources=all_sources,
        input_type=input_type,
        audio_file_id=audio_file_id
    )

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        patient_sources=patient_sources,
        external_sources=external_sources,
        history=updated_history
    )


# ==============================================================================
# Chat Session Management Endpoints (Strict Patient Data Isolation)
# ==============================================================================

@router.get("/chat/sessions", response_model=List[SessionSummary])
async def list_patient_sessions(
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Returns all chat sessions belonging strictly to the authenticated patient,
    sorted by most recently updated.
    """
    sessions = get_sessions_by_patient(current_patient.patient_id)
    summaries: List[SessionSummary] = []
    for s in sessions:
        summaries.append(SessionSummary(
            session_id=s["_id"],
            patient_id=s["patient_id"],
            title=s.get("title", "New Conversation"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at")
        ))
    return summaries


@router.post("/chat/sessions", response_model=SessionSummary)
async def create_new_session(
    request: Optional[CreateSessionRequest] = None,
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Creates a new empty chat session explicitly bound to the authenticated patient.
    """
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    title = request.title if request and request.title else "New Conversation"
    session_doc = create_session(
        session_id=session_id,
        patient_id=current_patient.patient_id,
        title=title
    )
    return SessionSummary(
        session_id=session_doc["_id"],
        patient_id=session_doc["patient_id"],
        title=session_doc["title"],
        created_at=session_doc["created_at"],
        updated_at=session_doc["updated_at"]
    )


@router.get("/chat/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_details(
    session_id: str,
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Retrieves full message history for a specific session ID.
    Enforces that session.patient_id == current_patient.patient_id.
    Returns 404 if session not found or belongs to another patient.
    """
    session = get_session_for_patient(session_id, current_patient.patient_id)
    if not session:
        # Prevent information leakage about other patients' sessions
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or not accessible."
        )

    messages = get_patient_session_history(session_id, current_patient.patient_id)
    return SessionDetailResponse(
        session_id=session["_id"],
        patient_id=session["patient_id"],
        title=session.get("title", "New Conversation"),
        messages=messages
    )


@router.delete("/chat/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_patient_session(
    session_id: str,
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Deletes a session and all its messages, verifying authenticated patient ownership.
    """
    session = get_session_for_patient(session_id, current_patient.patient_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or not accessible."
        )

    cleared = clear_session_for_patient(session_id, current_patient.patient_id)
    return DeleteSessionResponse(
        session_id=session_id,
        message="Session and message history deleted successfully.",
        cleared=cleared
    )


# ==============================================================================
# Chat Execution Endpoints
# ==============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Submits a user message to the multimodal RAG assistant.
    Security:
    - Derives patient identity strictly from authenticated JWT.
    - If request body supplies a conflicting patient_id, rejects the attempt.
    """
    if request.patient_id and request.patient_id.strip() != current_patient.patient_id:
        logger.warning(
            f"Security alert: Patient '{current_patient.patient_id}' attempted to access "
            f"data for patient '{request.patient_id}'."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-patient data access is forbidden."
        )

    return await process_chat_query(
        session_id=request.session_id,
        patient_id=current_patient.patient_id,
        message_text=request.message
    )


@router.delete("/chat/{session_id}", response_model=DeleteSessionResponse)
async def delete_session_legacy_endpoint(
    session_id: str,
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Legacy session delete endpoint, now protected with patient ownership check.
    """
    session = get_session_for_patient(session_id, current_patient.patient_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or not accessible."
        )

    cleared = clear_session_for_patient(session_id, current_patient.patient_id)
    return DeleteSessionResponse(
        session_id=session_id,
        message=f"Session history {'cleared successfully' if cleared else 'was already empty'}.",
        cleared=cleared
    )


@router.get("/chat/messages/{message_id}/audio")
async def stream_message_audio(
    message_id: str,
    current_patient: AuthenticatedPatient = Depends(get_current_patient_flexible),
):
    """
    Streams the stored voice recording binary directly from MongoDB GridFS.
    Security:
    - Verifies JWT (via Bearer header or ?token=<jwt> query parameter).
    - Enforces strict patient data isolation: message.patient_id MUST equal current_patient.patient_id.
    - If message not found or belongs to another patient, returns 404 to avoid leaking existence.
    """
    message_doc = get_message(message_id)
    if not message_doc or message_doc.get("patient_id") != current_patient.patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio recording not found or not accessible."
        )

    audio_file_id = message_doc.get("audio_file_id")
    if not audio_file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No audio recording attached to this message."
        )

    grid_out = get_audio_file(audio_file_id)
    if not grid_out:
        logger.warning(f"Message {message_id} references audio_file_id {audio_file_id} which does not exist in GridFS.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found in storage."
        )

    media_type = (grid_out.metadata or {}).get("content_type") if grid_out.metadata else "audio/wav"
    if not media_type:
        media_type = "audio/wav"
    filename = grid_out.filename or f"recording_{message_id}.wav"
    audio_bytes = grid_out.read()

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(audio_bytes)),
            "Content-Disposition": f'inline; filename="{filename}"',
        }
    )

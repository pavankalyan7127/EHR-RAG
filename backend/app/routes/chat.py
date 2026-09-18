import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import ChatRequest, ChatResponse, DeleteSessionResponse
from app.db.repositories import get_patient
from app.core.retrieval import retrieve_context, build_context_block
from app.core.generation import generate_answer
from app.chat.session_manager import (
    get_or_create_session,
    get_session_history,
    add_turn_to_session,
    clear_session_history,
    PatientSessionMismatchError
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Chat"])

async def process_chat_query(session_id: str, patient_id: str, message_text: str) -> ChatResponse:
    """
    Core RAG pipeline orchestration:
    1. Validates patient exists in MongoDB.
    2. Validates/creates session with patient ownership check.
    3. Retrieves patient EHR from MongoDB + external MedQuAD from FAISS.
    4. Fetches multi-turn history from MongoDB.
    5. Builds grounded context and generates response via Gemini.
    6. Persists conversation turn with source provenance to MongoDB.
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

    # 4. Context Assembly & History Retrieval
    context_block = build_context_block(patient_id, patient_records, external_records)
    history = get_session_history(session_id)

    # 5. Grounded Generation via Gemini
    try:
        answer = generate_answer(
            context_block=context_block,
            history=history,
            message=cleaned_message
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

    # 7. Persist Turn to MongoDB (User + Assistant Messages)
    updated_history = add_turn_to_session(
        session_id=session_id,
        patient_id=patient_id,
        user_message=cleaned_message,
        assistant_message=answer,
        sources=all_sources
    )

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        patient_sources=patient_sources,
        external_sources=external_sources,
        history=updated_history
    )

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    return await process_chat_query(
        session_id=request.session_id,
        patient_id=request.patient_id,
        message_text=request.message
    )

@router.delete("/chat/{session_id}", response_model=DeleteSessionResponse)
async def delete_session_endpoint(session_id: str):
    cleared = clear_session_history(session_id)
    return DeleteSessionResponse(
        session_id=session_id,
        message=f"Session history {'cleared successfully' if cleared else 'was already empty'}.",
        cleared=cleared
    )

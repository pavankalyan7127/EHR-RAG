import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import ChatRequest, ChatResponse, DeleteSessionResponse
from app.core.embeddings import vector_store
from app.core.retrieval import retrieve_context, build_context_block
from app.core.generation import generate_answer
from app.chat.session_manager import (
    get_session_history,
    add_turn_to_session,
    clear_session_history
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty."
        )

    patient_chunk = vector_store.get_patient_chunk(request.patient_id)
    if not patient_chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID '{request.patient_id}' not found in EHR database."
        )

    patient_record, external_records = retrieve_context(
        patient_id=request.patient_id,
        query=message,
        top_k_external=3
    )

    context_block = build_context_block(patient_record, external_records)
    history = get_session_history(request.session_id)

    try:
        answer = generate_answer(
            context_block=context_block,
            history=history,
            message=message
        )
    except Exception as e:
        logger.error(f"Generation failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}"
        )

    updated_history = add_turn_to_session(
        session_id=request.session_id,
        user_message=message,
        assistant_message=answer
    )

    patient_sources = [patient_record["chunk_id"]] if patient_record else []
    external_sources = [chunk["chunk_id"] for chunk in external_records]

    return ChatResponse(
        session_id=request.session_id,
        answer=answer,
        patient_sources=patient_sources,
        external_sources=external_sources,
        history=updated_history
    )

@router.delete("/chat/{session_id}", response_model=DeleteSessionResponse)
async def delete_session_endpoint(session_id: str):
    cleared = clear_session_history(session_id)
    return DeleteSessionResponse(
        session_id=session_id,
        message=f"Session history {'cleared successfully' if cleared else 'was already empty'}.",
        cleared=cleared
    )

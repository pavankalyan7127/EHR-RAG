import os
import tempfile
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status

from app.models.schemas import VoiceChatResponse
from app.core.asr import asr_manager
from app.core.auth import get_current_patient, AuthenticatedPatient
from app.routes.chat import process_chat_query
from app.db.repositories import save_audio_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Voice Chat"])


@router.post("/voice-chat", response_model=VoiceChatResponse)
async def voice_chat_endpoint(
    session_id: str = Form(..., description="Unique session ID"),
    audio: UploadFile = File(..., description="Audio file upload (wav, mp3, m4a, webm, etc.)"),
    patient_id: Optional[str] = Form(None, description="Optional patient ID (derived from JWT)"),
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Processes speech-to-text transcription + RAG answer for authenticated patient.
    Derives patient identity strictly from validated JWT.
    Persists original audio binary into MongoDB GridFS.
    """
    if patient_id and patient_id.strip() != current_patient.patient_id:
        logger.warning(
            f"Security alert: Patient '{current_patient.patient_id}' attempted voice chat "
            f"for patient '{patient_id}'."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-patient data access is forbidden."
        )

    if not audio.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file uploaded."
        )

    _, ext = os.path.splitext(audio.filename)
    if not ext:
        ext = ".wav"

    temp_file_path = None
    try:
        audio_bytes = await audio.read()
        logger.info(f"Received audio upload '{audio.filename}' of size {len(audio_bytes)} bytes.")

        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty (0 bytes)."
            )

        # 1. Save original audio binary to MongoDB GridFS
        content_type = audio.content_type or ("audio/wav" if ext == ".wav" else "audio/webm")
        audio_file_id = save_audio_file(
            audio_bytes=audio_bytes,
            filename=audio.filename,
            content_type=content_type,
            patient_id=current_patient.patient_id,
            session_id=session_id
        )

        # 2. Transcribe audio via local Whisper ASR
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_audio:
            temp_file_path = temp_audio.name
            temp_audio.write(audio_bytes)
            temp_audio.flush()

        transcribed_text = asr_manager.transcribe_audio_file(temp_file_path)

        if not transcribed_text or not transcribed_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not transcribe any speech from the provided audio."
            )

        # 3. Process chat query with input_type="voice" and audio_file_id reference
        chat_response = await process_chat_query(
            session_id=session_id,
            patient_id=current_patient.patient_id,
            message_text=transcribed_text,
            input_type="voice",
            audio_file_id=audio_file_id
        )

        # 4. Locate user message in history to extract generated audio_url
        user_msg = next(
            (m for m in reversed(chat_response.history) if m.role == "user" and m.audio_file_id == audio_file_id),
            None
        )
        audio_url = user_msg.audio_url if user_msg else f"/chat/messages/{audio_file_id}/audio"

        return VoiceChatResponse(
            session_id=chat_response.session_id,
            answer=chat_response.answer,
            patient_sources=chat_response.patient_sources,
            external_sources=chat_response.external_sources,
            history=chat_response.history,
            transcribed_text=transcribed_text,
            audio_file_id=audio_file_id,
            audio_url=audio_url
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice chat processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice chat processing failed: {str(e)}"
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as cleanup_err:
                logger.warning(f"Failed to delete temp audio file {temp_file_path}: {cleanup_err}")

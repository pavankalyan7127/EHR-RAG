import os
import shutil
import tempfile
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from app.models.schemas import VoiceChatResponse, ChatRequest
from app.core.asr import asr_manager
from app.routes.chat import chat_endpoint

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Voice Chat"])

@router.post("/voice-chat", response_model=VoiceChatResponse)
async def voice_chat_endpoint(
    session_id: str = Form(..., description="Unique session ID"),
    patient_id: str = Form(..., description="Patient ID"),
    audio: UploadFile = File(..., description="Audio file upload (wav, mp3, m4a, webm, etc.)")
):
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
        # Read uploaded bytes
        audio_bytes = await audio.read()
        logger.info(f"Received audio upload '{audio.filename}' of size {len(audio_bytes)} bytes.")

        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty (0 bytes)."
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_audio:
            temp_file_path = temp_audio.name
            temp_audio.write(audio_bytes)
            temp_audio.flush()

        transcribed_text = asr_manager.transcribe_audio_file(temp_file_path)


        if not transcribed_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not transcribe any speech from the provided audio."
            )

        chat_request = ChatRequest(
            session_id=session_id,
            patient_id=patient_id,
            message=transcribed_text
        )
        chat_response = await chat_endpoint(chat_request)

        return VoiceChatResponse(
            session_id=chat_response.session_id,
            answer=chat_response.answer,
            patient_sources=chat_response.patient_sources,
            external_sources=chat_response.external_sources,
            history=chat_response.history,
            transcribed_text=transcribed_text
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

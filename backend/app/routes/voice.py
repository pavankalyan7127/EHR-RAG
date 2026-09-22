import os
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status

from app.models.schemas import VoiceChatResponse
from app.core.auth import get_current_patient, AuthenticatedPatient
from app.routes.chat import process_chat_query
from app.db.repositories import save_audio_file
from app.services.nlp_client import MultilingualNLPClient, NLPServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Voice Chat"])

nlp_client = MultilingualNLPClient()
SUPPORTED_LANGUAGES = {"en", "bn", "gu", "hi", "mr", "pa", "ta", "te", "ur"}


@router.post("/voice-chat", response_model=VoiceChatResponse)
async def voice_chat_endpoint(
    session_id: str = Form(..., description="Unique session ID"),
    audio: UploadFile = File(..., description="Audio file upload (wav, mp3, m4a, webm, etc.)"),
    patient_id: Optional[str] = Form(None, description="Optional patient ID (derived from JWT)"),
    target_language: Optional[str] = Form(None, description="Optional target language code (e.g. 'en', 'bn', 'gu', 'hi', 'mr', 'pa', 'ta', 'te', 'ur')"),
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Processes multilingual speech input via Colab Indic ASR + neural translation,
    runs canonical English medical reasoning through process_chat_query(),
    and localizes the output into the target language with neural TTS audio.
    Derives patient identity strictly from validated JWT.
    Persists original recorded audio binary into MongoDB GridFS.
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

    # 1. Validate requested target language if explicitly provided
    requested_target = None
    if target_language:
        requested_target = target_language.strip().lower()
        if requested_target not in SUPPORTED_LANGUAGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported target language '{target_language}'. Supported languages: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )

    if not audio.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file uploaded."
        )

    _, ext = os.path.splitext(audio.filename)
    if not ext:
        ext = ".wav"

    try:
        audio_bytes = await audio.read()
        logger.info(f"Received audio upload '{audio.filename}' of size {len(audio_bytes)} bytes.")

        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty (0 bytes)."
            )

        # 2. Save original audio binary to MongoDB GridFS (preserves historical playback)
        content_type = audio.content_type or ("audio/wav" if ext == ".wav" else "audio/webm")
        audio_file_id = save_audio_file(
            audio_bytes=audio_bytes,
            filename=audio.filename,
            content_type=content_type,
            patient_id=current_patient.patient_id,
            session_id=session_id
        )

        # 3. Transcribe, identify language, and translate audio via Google Colab Multilingual NLP service
        try:
            nlp_voice = await nlp_client.process_voice_input(
                audio_bytes=audio_bytes,
                filename=audio.filename
            )
        except NLPServiceError as ne:
            logger.error(f"Multilingual NLP voice input processing error: {ne}")
            raise HTTPException(
                status_code=ne.status_code if ne.status_code and 400 <= ne.status_code < 600 else status.HTTP_502_BAD_GATEWAY,
                detail=f"Multilingual NLP service error during voice processing: {ne.message}"
            )
        except Exception as exc:
            logger.error(f"Unexpected error communicating with NLP voice service: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to process voice through multilingual NLP service."
            )

        detected_language = nlp_voice.get("detected_language") or "en"
        native_text = (nlp_voice.get("native_text") or "").strip()
        english_text = (nlp_voice.get("english_text") or "").strip()

        # Validate that speech was recognized
        if not native_text and not english_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not transcribe any speech from the provided audio."
            )

        query_text = english_text or native_text

        # 4. Determine output target language
        target_lang = requested_target or detected_language
        if target_lang not in SUPPORTED_LANGUAGES:
            target_lang = "en"

        # 5. Process core RAG query using the translated English query
        chat_response = await process_chat_query(
            session_id=session_id,
            patient_id=current_patient.patient_id,
            message_text=query_text,
            input_type="voice",
            audio_file_id=audio_file_id
        )

        # 6. Localize canonical English medical response and generate neural TTS audio
        try:
            localized = await nlp_client.localize_output(
                english_response=chat_response.answer,
                target_language=target_lang
            )
        except NLPServiceError as ne:
            logger.error(f"Multilingual NLP output localization error: {ne}")
            raise HTTPException(
                status_code=ne.status_code if ne.status_code and 400 <= ne.status_code < 600 else status.HTTP_502_BAD_GATEWAY,
                detail=f"Multilingual NLP service error during output localization: {ne.message}"
            )
        except Exception as exc:
            logger.error(f"Unexpected error during output localization: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to localize response through multilingual NLP service."
            )

        localized_answer = localized.get("native_text") or chat_response.answer
        audio_base64 = localized.get("audio_base64")
        audio_format = localized.get("audio_format", "wav")

        # 7. Locate user message in history to extract generated audio_url
        user_msg = next(
            (m for m in reversed(chat_response.history) if m.role == "user" and m.audio_file_id == audio_file_id),
            None
        )
        audio_url = user_msg.audio_url if user_msg else f"/chat/messages/{audio_file_id}/audio"

        # 8. transcribed_text must contain the ORIGINAL NATIVE-LANGUAGE transcription
        original_transcription = native_text or english_text

        return VoiceChatResponse(
            session_id=chat_response.session_id,
            answer=localized_answer,
            canonical_answer=chat_response.answer,
            patient_sources=chat_response.patient_sources,
            external_sources=chat_response.external_sources,
            history=chat_response.history,
            language=target_lang,
            audio_base64=audio_base64,
            audio_format=audio_format,
            transcribed_text=original_transcription,
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

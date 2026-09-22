import logging
import mimetypes
from typing import Dict, Any, Optional
import httpx

from app.config import NLP_SERVICE_URL, NLP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class NLPServiceError(Exception):
    """
    Application-level exception raised when the external multilingual NLP service
    is unavailable or returns an error response.
    """
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details

    def __str__(self) -> str:
        if self.status_code:
            return f"[Status {self.status_code}] {self.message}"
        return self.message


class MultilingualNLPClient:
    """
    Async HTTP client for interacting with the external multilingual NLP service
    (supporting text processing, voice ASR, translation, and neural TTS localization).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.base_url = (base_url or NLP_SERVICE_URL).rstrip("/")
        self.timeout = httpx.Timeout(timeout=timeout or NLP_TIMEOUT_SECONDS, connect=10.0)
        self.headers = {
            "ngrok-skip-browser-warning": "true",
            "Accept": "application/json",
        }

    def _handle_request_error(self, exc: Exception) -> NLPServiceError:
        logger.error(f"Multilingual NLP service connection failed: {exc}", exc_info=True)
        if isinstance(exc, httpx.TimeoutException):
            return NLPServiceError(
                message="Multilingual NLP service timed out while processing the request.",
                status_code=504
            )
        return NLPServiceError(
            message="Multilingual NLP service is currently unavailable. Please verify service connectivity.",
            status_code=503
        )

    def _handle_response_error(self, response: httpx.Response) -> NLPServiceError:
        error_msg = f"Multilingual NLP service returned HTTP status {response.status_code}."
        detail = None
        try:
            data = response.json()
            if isinstance(data, dict):
                detail = data.get("detail") or data.get("message")
                if detail:
                    error_msg = f"Multilingual NLP service error ({response.status_code}): {detail}"
        except Exception:
            if response.text:
                detail = response.text[:200]
                error_msg = f"Multilingual NLP service error ({response.status_code}): {detail}"

        logger.error(f"Multilingual NLP service error [{response.status_code}]: {detail or response.text}")
        return NLPServiceError(
            message=error_msg,
            status_code=response.status_code,
            details=detail
        )

    async def process_text_input(self, text: str) -> Dict[str, Any]:
        """
        Send text to the multilingual NLP service to detect language and translate to English.

        POST /nlp/input/text
        Payload: {"text": text}
        Returns:
            {
                "input_type": "text",
                "detected_language": "ta",
                "native_text": "...",
                "english_text": "..."
            }
        """
        url = f"{self.base_url}/nlp/input/text"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.post(url, json={"text": text})
                if response.is_error:
                    raise self._handle_response_error(response)
                return response.json()
        except httpx.RequestError as exc:
            raise self._handle_request_error(exc) from exc

    async def process_voice_input(self, audio_bytes: bytes, filename: str = "audio.wav") -> Dict[str, Any]:
        """
        Send audio file bytes to the multilingual NLP service to transcribe,
        detect language, and translate to English.

        POST /nlp/input/voice
        Multipart/form-data: audio = uploaded audio bytes
        Returns:
            {
                "input_type": "voice",
                "detected_language": "ta",
                "native_text": "...",
                "english_text": "...",
                "language_confidence": 0.99
            }
        """
        url = f"{self.base_url}/nlp/input/voice"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {
            "audio": (filename, audio_bytes, content_type)
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.post(url, files=files)
                if response.is_error:
                    raise self._handle_response_error(response)
                return response.json()
        except httpx.RequestError as exc:
            raise self._handle_request_error(exc) from exc

    async def localize_output(self, english_response: str, target_language: str) -> Dict[str, Any]:
        """
        Translate English response to the target language and generate neural TTS audio.

        POST /nlp/output
        Payload:
            {
                "english_response": english_response,
                "target_language": target_language
            }
        Returns:
            {
                "target_language": "ta",
                "native_text": "...",
                "audio_base64": "...",
                "audio_format": "wav"
            }
        """
        url = f"{self.base_url}/nlp/output"
        payload = {
            "english_response": english_response,
            "target_language": target_language
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.post(url, json=payload)
                if response.is_error:
                    raise self._handle_response_error(response)
                return response.json()
        except httpx.RequestError as exc:
            raise self._handle_request_error(exc) from exc

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health status of the multilingual NLP service.

        GET /health
        Returns JSON response from the NLP service.
        """
        url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.get(url)
                if response.is_error:
                    raise self._handle_response_error(response)
                return response.json()
        except httpx.RequestError as exc:
            raise self._handle_request_error(exc) from exc


# Default client instance
_default_client = MultilingualNLPClient()


# Module-level convenience functions
async def process_text_input(text: str) -> Dict[str, Any]:
    """Module-level helper delegating to default MultilingualNLPClient."""
    return await _default_client.process_text_input(text)


async def process_voice_input(audio_bytes: bytes, filename: str = "audio.wav") -> Dict[str, Any]:
    """Module-level helper delegating to default MultilingualNLPClient."""
    return await _default_client.process_voice_input(audio_bytes, filename)


async def localize_output(english_response: str, target_language: str) -> Dict[str, Any]:
    """Module-level helper delegating to default MultilingualNLPClient."""
    return await _default_client.localize_output(english_response, target_language)


async def health_check() -> Dict[str, Any]:
    """Module-level helper delegating to default MultilingualNLPClient."""
    return await _default_client.health_check()

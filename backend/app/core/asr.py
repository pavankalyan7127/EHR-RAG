import logging
import os
import shutil
import tempfile
from typing import Optional
import whisper
from app.config import WHISPER_MODEL_NAME

# Ensure ffmpeg binary path from imageio_ffmpeg is added to PATH if available
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    # Ensure a file named ffmpeg.exe exists in that folder
    standard_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    if not os.path.exists(standard_ffmpeg) and os.path.exists(ffmpeg_exe):
        try:
            shutil.copyfile(ffmpeg_exe, standard_ffmpeg)
        except Exception:
            pass
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception as e:
    pass


logger = logging.getLogger(__name__)

class ASRManager:
    """
    Manages loading of the OpenAI Whisper ASR model for voice transcription.
    """
    def __init__(self):
        self.model: Optional[whisper.Whisper] = None

    def initialize(self):
        """Loads Whisper speech-to-text model into memory."""
        logger.info(f"Loading Whisper ASR model ({WHISPER_MODEL_NAME})...")
        self.model = whisper.load_model(WHISPER_MODEL_NAME)
        logger.info("Whisper ASR model loaded successfully.")

    def transcribe_audio_file(self, file_path: str) -> str:
        """
        Transcribes an audio file into text using Whisper.
        """
        if self.model is None:
            self.initialize()

        logger.info(f"Transcribing audio file: {file_path}")
        result = self.model.transcribe(
            file_path,
            fp16=False,
            language="en",
            temperature=0.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False
        )
        transcribed_text = result.get("text", "").strip()
        logger.info(f"Transcription complete: '{transcribed_text}'")
        return transcribed_text


asr_manager = ASRManager()

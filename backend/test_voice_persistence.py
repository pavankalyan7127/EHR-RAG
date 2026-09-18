import io
import wave
import struct
import math
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_access_token
from app.db.repositories import (
    get_message,
    get_audio_file,
    delete_messages_by_session,
    delete_session_for_patient,
    get_session_messages
)


def generate_dummy_wav(duration_sec=0.5, sample_rate=16000) -> bytes:
    """Generates a small valid WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        total_samples = int(duration_sec * sample_rate)
        frames = bytearray()
        for i in range(total_samples):
            val = int(32767.0 * 0.2 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wav_file.writeframes(frames)
    return buf.getvalue()


def test_voice_persistence_and_streaming():
    with TestClient(app) as client:
        patient_id_1 = "P017"
        patient_id_2 = "P018"
        token_p1 = create_access_token(patient_id_1)
        token_p2 = create_access_token(patient_id_2)

        wav_bytes = generate_dummy_wav()
        session_id = f"test_voice_sess_{patient_id_1}"

        # Mock ASR transcribe and generation so test doesn't call external API or spend quota
        with patch("app.core.asr.asr_manager.transcribe_audio_file", return_value="What are my recent lab results?"), \
             patch("app.routes.chat.generate_answer", return_value="Your recent lab results are normal."):

            response = client.post(
                "/voice-chat",
                data={"session_id": session_id, "patient_id": patient_id_1},
                files={"audio": ("patient_voice.wav", io.BytesIO(wav_bytes), "audio/wav")},
                headers={"Authorization": f"Bearer {token_p1}"}
            )

            assert response.status_code == 200, f"Voice chat failed: {response.text}"
            data = response.json()
            assert data["session_id"] == session_id
            assert data["transcribed_text"] == "What are my recent lab results?"
            assert data["answer"] == "Your recent lab results are normal."
            assert data["audio_file_id"] is not None
            assert data["audio_url"] is not None
            audio_file_id = data["audio_file_id"]

        # 1. Verify GridFS storage
        grid_out = get_audio_file(audio_file_id)
        assert grid_out is not None, "Audio file was not persisted in GridFS!"
        stored_bytes = grid_out.read()
        assert len(stored_bytes) == len(wav_bytes), "Stored audio byte size mismatch!"
        assert stored_bytes == wav_bytes, "Stored audio binary content does not match uploaded bytes!"

        # 2. Verify MongoDB message document
        messages = get_session_messages(session_id)
        assert len(messages) >= 2
        user_msg = next((m for m in messages if m.get("role") == "user" and m.get("audio_file_id") == audio_file_id), None)
        assert user_msg is not None, "User message not found in messages collection!"
        assert user_msg["input_type"] == "voice"
        assert user_msg["patient_id"] == patient_id_1
        user_msg_id = user_msg["_id"]

        # 3. Verify Audio Streaming Endpoint with Bearer token
        stream_res_bearer = client.get(
            f"/chat/messages/{user_msg_id}/audio",
            headers={"Authorization": f"Bearer {token_p1}"}
        )
        assert stream_res_bearer.status_code == 200, f"Bearer streaming failed: {stream_res_bearer.text}"
        assert stream_res_bearer.content == wav_bytes
        assert "audio/wav" in stream_res_bearer.headers["Content-Type"]
        assert stream_res_bearer.headers.get("Accept-Ranges") == "bytes"

        # 4. Verify Audio Streaming Endpoint with ?token=<jwt> (Native HTML5 <audio> tag)
        stream_res_query = client.get(
            f"/chat/messages/{user_msg_id}/audio?token={token_p1}"
        )
        assert stream_res_query.status_code == 200, f"Query token streaming failed: {stream_res_query.text}"
        assert stream_res_query.content == wav_bytes

        # 5. Strict Patient Isolation: P018 MUST NOT access P017's audio recording (returns 404)
        res_iso_bearer = client.get(
            f"/chat/messages/{user_msg_id}/audio",
            headers={"Authorization": f"Bearer {token_p2}"}
        )
        assert res_iso_bearer.status_code == 404, "Security violation: Cross-patient audio accessible via Bearer token!"

        res_iso_query = client.get(
            f"/chat/messages/{user_msg_id}/audio?token={token_p2}"
        )
        assert res_iso_query.status_code == 404, "Security violation: Cross-patient audio accessible via Query token!"

        # 6. Verify Session History endpoint returns audio_url and input_type
        history_res = client.get(
            f"/chat/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token_p1}"}
        )
        assert history_res.status_code == 200
        hist_messages = history_res.json()["messages"]
        hist_user_msg = next((m for m in hist_messages if m["role"] == "user" and m.get("audio_file_id") == audio_file_id), None)
        assert hist_user_msg is not None
        assert hist_user_msg["input_type"] == "voice"
        assert hist_user_msg["audio_url"] == f"/chat/messages/{user_msg_id}/audio"

        # 7. Clean up session and verify GridFS file deletion
        del_res = client.delete(
            f"/chat/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token_p1}"}
        )
        assert del_res.status_code == 200

        # Verify GridFS file was cleaned up along with session messages
        grid_out_after_delete = get_audio_file(audio_file_id)
        assert grid_out_after_delete is None, "GridFS audio file was not deleted upon session deletion!"


def test_text_chat_backwards_compatibility():
    """Verifies that standard text chat still saves input_type='text' and audio_file_id=None."""
    with TestClient(app) as client:
        patient_id = "P017"
        token = create_access_token(patient_id)
        session_id = f"test_text_sess_{patient_id}"

        with patch("app.routes.chat.generate_answer", return_value="Here is text advice."):
            res = client.post(
                "/chat",
                json={"session_id": session_id, "patient_id": patient_id, "message": "Hello doctor"},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["answer"] == "Here is text advice."

        # Check messages in DB
        messages = get_session_messages(session_id)
        user_msg = next((m for m in messages if m.get("role") == "user"), None)
        assert user_msg is not None
        assert user_msg["input_type"] == "text"
        assert user_msg.get("audio_file_id") is None

        # Clean up test session
        client.delete(
            f"/chat/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"}
        )


if __name__ == "__main__":
    pytest.main(["-v", "test_voice_persistence.py"])

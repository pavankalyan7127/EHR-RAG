import sys
import os
import io
import json
import base64
import asyncio
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from app.main import app
from app.services.nlp_client import localize_output
from app.routes import chat as chat_module
from app.routes import voice as voice_module
from app.db.repositories import get_audio_file

def run_all_tests():
    print("=" * 70)
    print("STARTING COMPLETE BACKEND MULTILINGUAL INTEGRATION TESTS")
    print("=" * 70)

    with TestClient(app) as client:
        # Authentication
        login_res = client.post("/auth/login", json={"patient_id": "P001", "password": "P001"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print("[AUTH] Successfully authenticated as patient P001.")

        # Create a fresh test session
        sess_res = client.post("/chat/sessions", json={"title": "Multilingual Integration Session"}, headers=auth_headers)
        assert sess_res.status_code == 200, f"Failed to create session: {sess_res.text}"
        session_id = sess_res.json()["session_id"]
        print(f"[SESSION] Created test session: {session_id}")

        test_results = {}

        import time
        def safe_post(url, **kwargs):
            res = client.post(url, **kwargs)
            if res.status_code == 429:
                print("  [RATE LIMIT] Hit Gemini rate limit (429), waiting 35s to clear window...")
                time.sleep(35)
                res = client.post(url, **kwargs)
            elif res.status_code == 500:
                print("  [RETRY] Hit transient 500, waiting 5s to retry...")
                time.sleep(5)
                res = client.post(url, **kwargs)
            return res

        # ----------------------------------------------------
        # TEST 1: English TEXT chat
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 1: English TEXT chat ---")
        query_en = "What medications am I currently prescribed?"
        res1 = safe_post("/chat", json={
            "session_id": session_id,
            "patient_id": "P001",
            "message": query_en,
            "target_language": "en"
        }, headers=auth_headers)

        assert res1.status_code == 200, f"Test 1 failed with {res1.status_code}: {res1.text}"
        data1 = res1.json()
        assert data1["session_id"] == session_id
        assert data1["language"] == "en"
        assert data1["canonical_answer"] is not None and len(data1["canonical_answer"]) > 0
        assert data1["answer"] is not None and len(data1["answer"]) > 0
        assert "patient_sources" in data1
        assert "external_sources" in data1
        assert "history" in data1 and len(data1["history"]) > 0
        print(f"  [PASS] Answer (EN): {data1['answer'][:80]}...")
        print(f"  [PASS] Canonical Answer: {data1['canonical_answer'][:80]}...")
        print(f"  [PASS] Language: {data1['language']}")
        print(f"  [PASS] Sources: patient={len(data1['patient_sources'])}, external={len(data1['external_sources'])}, history={len(data1['history'])}")
        test_results["TEST 1 (English TEXT)"] = "PASSED"

        # ----------------------------------------------------
        # TEST 2: Tamil TEXT chat
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 2: Tamil TEXT chat ---")
        query_ta = "எனக்கு என்ன மருந்துகள் பரிந்துரைக்கப்பட்டுள்ளன?"
        res2 = safe_post("/chat", json={
            "session_id": session_id,
            "patient_id": "P001",
            "message": query_ta
        }, headers=auth_headers)

        assert res2.status_code == 200, f"Test 2 failed with {res2.status_code}: {res2.text}"
        data2 = res2.json()
        assert data2["session_id"] == session_id
        assert data2["language"] == "ta"
        assert data2["canonical_answer"] is not None and len(data2["canonical_answer"]) > 0
        assert data2["answer"] is not None and len(data2["answer"]) > 0
        assert data2["audio_base64"] is not None and len(data2["audio_base64"]) > 0
        assert data2["audio_format"] == "wav"
        assert "patient_sources" in data2
        assert "external_sources" in data2
        assert "history" in data2 and len(data2["history"]) > 0
        print(f"  [PASS] Answer (TA): {data2['answer'][:80]}...")
        print(f"  [PASS] Canonical Answer (EN): {data2['canonical_answer'][:80]}...")
        print(f"  [PASS] Language: {data2['language']}")
        print(f"  [PASS] Audio Base64 length: {len(data2['audio_base64'])}, format: {data2['audio_format']}")
        test_results["TEST 2 (Tamil TEXT)"] = "PASSED"

        # Save canonical answer for Test 4
        canonical_for_switching = data2["canonical_answer"]

        # ----------------------------------------------------
        # TEST 3: Voice chat
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 3: Voice chat ---")
        async def get_test_speech_audio():
            res = await localize_output("வணக்கம் எனக்கு என்ன மருந்துகள் பரிந்துரைக்கப்பட்டுள்ளன?", "ta")
            return base64.b64decode(res["audio_base64"])

        audio_bytes = asyncio.run(get_test_speech_audio())
        assert len(audio_bytes) > 1000, "Failed to generate speech audio test file."

        files = {"audio": ("patient_voice.wav", audio_bytes, "audio/wav")}
        voice_data = {
            "session_id": session_id,
            "patient_id": "P001"
        }

        time.sleep(3)
        res3 = safe_post("/voice-chat", data=voice_data, files=files, headers=auth_headers)
        assert res3.status_code == 200, f"Test 3 failed with {res3.status_code}: {res3.text}"
        data3 = res3.json()

        assert data3["session_id"] == session_id
        assert data3["transcribed_text"] is not None and len(data3["transcribed_text"]) > 0
        assert data3["canonical_answer"] is not None and len(data3["canonical_answer"]) > 0
        assert data3["answer"] is not None and len(data3["answer"]) > 0
        assert data3["audio_file_id"] is not None
        assert data3["audio_url"] is not None
        assert data3["audio_base64"] is not None and len(data3["audio_base64"]) > 0
        assert data3["audio_format"] == "wav"

        # Verify MongoDB GridFS persistence
        grid_out = get_audio_file(data3["audio_file_id"])
        assert grid_out is not None, "GridFS audio binary not found in MongoDB!"
        stored_bytes = grid_out.read()
        assert len(stored_bytes) == len(audio_bytes), "GridFS stored audio bytes size mismatch!"

        print(f"  [PASS] Transcribed Text (Original Native): {data3['transcribed_text']}")
        print(f"  [PASS] Canonical Answer: {data3['canonical_answer'][:80]}...")
        print(f"  [PASS] Localized Answer: {data3['answer'][:80]}...")
        print(f"  [PASS] Language: {data3['language']}")
        print(f"  [PASS] GridFS audio_file_id: {data3['audio_file_id']} (verified in MongoDB)")
        print(f"  [PASS] TTS Audio Base64 length: {len(data3['audio_base64'])}")
        test_results["TEST 3 (Voice chat)"] = "PASSED"

        # ----------------------------------------------------
        # TEST 4: Language switching
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 4: Language switching ---")
        with patch.object(chat_module, "process_chat_query", wraps=chat_module.process_chat_query) as mock_pcq:
            # Switch to Hindi
            res4_hi = client.post("/chat/localize", json={
                "english_response": canonical_for_switching,
                "target_language": "hi"
            })
            assert res4_hi.status_code == 200, f"Hindi localization failed: {res4_hi.text}"
            data4_hi = res4_hi.json()
            assert data4_hi["target_language"] == "hi"
            assert len(data4_hi["native_text"]) > 0
            assert data4_hi["audio_base64"] is not None and len(data4_hi["audio_base64"]) > 0
            assert data4_hi["audio_format"] == "wav"
            print(f"  [PASS] Hindi Localized text: {data4_hi['native_text'][:80]}...")
            print(f"  [PASS] Hindi Audio Base64 length: {len(data4_hi['audio_base64'])}")

            # Switch to Telugu
            res4_te = client.post("/chat/localize", json={
                "english_response": canonical_for_switching,
                "target_language": "te"
            })
            assert res4_te.status_code == 200, f"Telugu localization failed: {res4_te.text}"
            data4_te = res4_te.json()
            assert data4_te["target_language"] == "te"
            assert len(data4_te["native_text"]) > 0
            assert data4_te["audio_base64"] is not None and len(data4_te["audio_base64"]) > 0
            assert data4_te["audio_format"] == "wav"
            print(f"  [PASS] Telugu Localized text: {data4_te['native_text'][:80]}...")
            print(f"  [PASS] Telugu Audio Base64 length: {len(data4_te['audio_base64'])}")

            assert mock_pcq.call_count == 0, "process_chat_query was called during localization!"
            print("  [PASS] Verified ZERO calls to process_chat_query during language switching!")

        test_results["TEST 4 (Language switching)"] = "PASSED"

        # ----------------------------------------------------
        # TEST 5: Backward compatibility
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 5: Backward compatibility ---")
        res5_text = safe_post("/chat", json={
            "session_id": session_id,
            "patient_id": "P001",
            "message": "Can I take aspirin with my medication?"
        }, headers=auth_headers)
        assert res5_text.status_code == 200, f"Legacy text request failed: {res5_text.text}"
        data5_text = res5_text.json()
        assert data5_text["language"] == "en"
        print(f"  [PASS] Text without target_language defaulted to: '{data5_text['language']}'")

        res5_voice = safe_post("/voice-chat", data={
            "session_id": session_id,
            "patient_id": "P001"
        }, files={"audio": ("voice_legacy.wav", audio_bytes, "audio/wav")}, headers=auth_headers)
        assert res5_voice.status_code == 200, f"Legacy voice request failed: {res5_voice.text}"
        data5_voice = res5_voice.json()
        assert data5_voice["language"] in ["en", "bn", "gu", "hi", "mr", "pa", "ta", "te", "ur"]
        print(f"  [PASS] Voice without target_language detected language: '{data5_voice['language']}'")

        test_results["TEST 5 (Backward compatibility)"] = "PASSED"

        # ----------------------------------------------------
        # TEST 6: Error handling
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 6: Error handling ---")
        res6_unsupported = client.post("/chat/localize", json={
            "english_response": "Take medicine twice daily.",
            "target_language": "fr"
        })
        assert res6_unsupported.status_code == 400
        assert "Unsupported target language" in res6_unsupported.json()["detail"]
        print("  [PASS] Unsupported language 'fr' rejected with HTTP 400")

        res6_missing = client.post("/chat/localize", json={
            "target_language": "hi"
        })
        assert res6_missing.status_code == 422
        print("  [PASS] Missing required fields rejected with HTTP 422")

        res6_conflict = client.post("/chat", json={
            "session_id": session_id,
            "patient_id": "P002",
            "message": "Hello doctor"
        }, headers=auth_headers)
        assert res6_conflict.status_code == 403
        print("  [PASS] Cross-patient data access rejected with HTTP 403")

        test_results["TEST 6 (Error handling)"] = "PASSED"

        # ----------------------------------------------------
        # TEST 7: Medical reasoning duplication check
        # ----------------------------------------------------
        print("\n--- RUNNING TEST 7: Medical reasoning duplication check ---")
        with patch.object(chat_module, "process_chat_query", wraps=chat_module.process_chat_query) as mock_pcq_chat:
            res7_chat = safe_post("/chat", json={
                "session_id": session_id,
                "patient_id": "P001",
                "message": "What is my allergy history?",
                "target_language": "en"
            }, headers=auth_headers)
            assert res7_chat.status_code == 200
            assert mock_pcq_chat.call_count == 1
            print(f"  [PASS] /chat executed process_chat_query() exactly {mock_pcq_chat.call_count} time.")

        with patch.object(voice_module, "process_chat_query", wraps=voice_module.process_chat_query) as mock_pcq_voice:
            res7_voice = safe_post("/voice-chat", data={
                "session_id": session_id,
                "patient_id": "P001"
            }, files={"audio": ("voice_dup.wav", audio_bytes, "audio/wav")}, headers=auth_headers)
            assert res7_voice.status_code == 200
            assert mock_pcq_voice.call_count == 1
            print(f"  [PASS] /voice-chat executed process_chat_query() exactly {mock_pcq_voice.call_count} time.")

        with patch.object(chat_module, "process_chat_query", wraps=chat_module.process_chat_query) as mock_pcq_loc:
            res7_loc = client.post("/chat/localize", json={
                "english_response": "Take paracetamol 500mg.",
                "target_language": "hi"
            })
            assert res7_loc.status_code == 200
            assert mock_pcq_loc.call_count == 0
            print(f"  [PASS] /chat/localize executed process_chat_query() exactly {mock_pcq_loc.call_count} times.")

        test_results["TEST 7 (Reasoning duplication check)"] = "PASSED"

        print("\n" + "=" * 70)
        print("ALL 7 TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        for t_name, t_stat in test_results.items():
            print(f"{t_name:40}: {t_stat}")

if __name__ == "__main__":
    run_all_tests()

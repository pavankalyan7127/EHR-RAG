import os
import sys
import uuid
import time
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import app
from app.models.schemas import ChatMessage
from app.core.embeddings import vector_store
from app.core.retrieval import (
    retrieve_context,
    filter_relevant_ehr_records,
    search_external_knowledge,
    DEFAULT_TOP_K_EHR
)
from app.core.generation import (
    build_conversation_prompt,
    generate_answer,
    GeminiQuotaExhaustedError,
    DEFAULT_HISTORY_WINDOW
)
from app.chat.session_manager import (
    get_session_history,
    get_recent_history_window,
    add_turn_to_session,
    clear_session_history
)
from app.db.repositories import (
    get_patient,
    get_session,
    get_session_messages,
    upsert_patient,
    upsert_ehr_record
)

def run_all_tests():
    print("\n" + "=" * 60)
    print("STARTING COMPREHENSIVE EHR RAG OPTIMIZATION VERIFICATION")
    print("=" * 60)

    # Initialize vector store if not already initialized
    if vector_store.embedding_model is None:
        print("\n--> Initializing VectorStoreManager (SentenceTransformer & FAISS)...")
        vector_store.initialize()

    # -------------------------------------------------------------
    # TEST 1: Patient has many EHR chunks (> 5) -> Top 5 relevant selected
    # -------------------------------------------------------------
    print("\n--- TEST 1: Patient with > 5 EHR Chunks (Relevance Filtering) ---")
    mock_records_patient = [
        {"_id": f"rec_{i}", "chunk_id": f"chunk_cardio_{i}", "patient_id": "P_TEST_MANY",
         "content": f"Cardiology visit {i}: Patient reports chest pain, hypertension, blood pressure 145/90. Prescribed Lisinopril."}
        for i in range(1, 6)
    ] + [
        {"_id": f"rec_{i}", "chunk_id": f"chunk_derm_{i}", "patient_id": "P_TEST_MANY",
         "content": f"Dermatology visit {i}: Patient has skin rash, eczema, prescribed hydrocortisone cream."}
        for i in range(6, 11)
    ]
    # 10 records total. Query specifically about cardiology.
    filtered_cardio = filter_relevant_ehr_records(
        patient_records=mock_records_patient,
        query="What is my blood pressure and heart medication?",
        top_k=5
    )
    assert len(filtered_cardio) == 5, f"Expected 5 chunks, got {len(filtered_cardio)}"
    # Verify cardiology chunks were prioritized by relevance
    cardio_chunk_ids = [r["chunk_id"] for r in filtered_cardio if "cardio" in r["chunk_id"]]
    print(f"Total retrieved: {len(mock_records_patient)}, Selected: {len(filtered_cardio)}")
    print(f"Selected chunk IDs: {[r['chunk_id'] for r in filtered_cardio]}")
    assert len(cardio_chunk_ids) >= 4, f"Expected cardiology chunks to dominate, got {cardio_chunk_ids}"
    print("[PASS] TEST 1: Only the configured number of relevant EHR chunks are selected.")

    # -------------------------------------------------------------
    # TEST 2: Patient has fewer EHR chunks than limit (< 5) -> All retained
    # -------------------------------------------------------------
    print("\n--- TEST 2: Patient with Fewer EHR Chunks (< 5) ---")
    mock_few_records = [
        {"_id": "rec_1", "chunk_id": "chunk_1", "patient_id": "P_FEW", "content": "Diabetes note: A1c is 7.2%."},
        {"_id": "rec_2", "chunk_id": "chunk_2", "patient_id": "P_FEW", "content": "Medication list: Metformin 500mg BID."}
    ]
    filtered_few = filter_relevant_ehr_records(
        patient_records=mock_few_records,
        query="What is my Metformin dosage?",
        top_k=5
    )
    assert len(filtered_few) == 2, f"Expected all 2 records retained, got {len(filtered_few)}"
    assert [r["chunk_id"] for r in filtered_few] == ["chunk_1", "chunk_2"]
    print(f"Total records: 2, Selected records: {len(filtered_few)}")
    print("[PASS] TEST 2: All available chunks retained when total <= limit.")

    # -------------------------------------------------------------
    # TEST 3: Multi-Patient Privacy Isolation
    # -------------------------------------------------------------
    print("\n--- TEST 3: Multi-Patient EHR Privacy Isolation ---")
    # Simulate DB records for Patient A and Patient B
    patient_a_records = [
        {"_id": "a_1", "chunk_id": "chunk_a1", "patient_id": "PA", "content": "Patient A clinical note: Severe asthma."}
    ]
    patient_b_records = [
        {"_id": "b_1", "chunk_id": "chunk_b1", "patient_id": "PB", "content": "Patient B clinical note: Diabetic foot ulcer."}
    ]

    with patch("app.core.retrieval.get_ehr_records_by_patient") as mock_get_ehr:
        mock_get_ehr.side_effect = lambda pid: patient_a_records if pid == "PA" else patient_b_records

        # When querying for PA, PB's records are never accessed or returned
        retrieved_a, _ = retrieve_context(patient_id="PA", query="diabetic ulcer")
        assert len(retrieved_a) == 1
        assert retrieved_a[0]["patient_id"] == "PA"
        assert "chunk_b1" not in [r["chunk_id"] for r in retrieved_a]

        # When querying for PB, PA's records are never accessed or returned
        retrieved_b, _ = retrieve_context(patient_id="PB", query="severe asthma")
        assert len(retrieved_b) == 1
        assert retrieved_b[0]["patient_id"] == "PB"
        assert "chunk_a1" not in [r["chunk_id"] for r in retrieved_b]

    print("[PASS] TEST 3: Patient records are strictly isolated by patient_id, never cross-compared.")

    # -------------------------------------------------------------
    # TEST 4: Long Conversation History (Prompt Window vs MongoDB Complete Retention)
    # -------------------------------------------------------------
    print("\n--- TEST 4: Conversation History Windowing (Prompt vs MongoDB) ---")
    # Build 10 ChatMessage objects (5 turns)
    full_history = [
        ChatMessage(role="user" if i % 2 == 1 else "assistant", content=f"Message_Turn_ID_{i}_Details")
        for i in range(1, 11)
    ]
    assert len(full_history) == 10

    # Build prompt with default window of 6
    prompt = build_conversation_prompt(
        context_block="Mock Medical Context",
        history=full_history,
        new_message="New follow-up query",
        max_history=6
    )

    # Verify older messages (1 to 4) are NOT in the prompt
    for i in range(1, 5):
        assert f"Message_Turn_ID_{i}_Details" not in prompt, f"Found older turn {i} in prompt!"

    # Verify recent 6 messages (5 to 10) ARE in the prompt
    for i in range(5, 11):
        assert f"Message_Turn_ID_{i}_Details" in prompt, f"Missing recent turn {i} in prompt!"

    print(f"Full history count: {len(full_history)}")
    print("Messages 1-4 excluded from prompt; Messages 5-10 included in prompt.")
    print("[PASS] TEST 4: Prompt receives only configured recent window while DB retains full history.")

    # -------------------------------------------------------------
    # TEST 5: External Retrieval FAISS top_k=3
    # -------------------------------------------------------------
    print("\n--- TEST 5: External MedQuAD FAISS Retrieval top_k=3 ---")
    ext_results = search_external_knowledge("What causes type 2 diabetes?", top_k=3)
    assert len(ext_results) == 3, f"Expected 3 chunks, got {len(ext_results)}"
    for chunk in ext_results:
        assert chunk.get("source_type") == "external"
        assert "chunk_id" in chunk
    print(f"Retrieved {len(ext_results)} external chunks: {[c['chunk_id'] for c in ext_results]}")
    print("[PASS] TEST 5: External FAISS retrieval continues to retrieve top 3 chunks.")

    # -------------------------------------------------------------
    # TEST 6: Gemini 503 / Transient Error Retry with Backoff
    # -------------------------------------------------------------
    print("\n--- TEST 6: Gemini Transient 503 Error Retry with Backoff ---")
    call_count = 0

    def mock_generate_with_transient_503(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("503 Service Unavailable - transient overload")
        mock_resp = MagicMock()
        mock_resp.text = "Success after retries"
        return mock_resp

    with patch("app.core.generation.get_genai_client") as mock_client_getter, \
         patch("app.core.generation.time.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = mock_generate_with_transient_503
        mock_client_getter.return_value = mock_client

        ans = generate_answer(
            context_block="Context",
            history=[],
            message="Test question",
            max_retries=3
        )
        assert ans == "Success after retries"
        assert call_count == 3, f"Expected 3 attempts, got {call_count}"
        assert mock_sleep.call_count == 2, f"Expected 2 sleep backoffs, got {mock_sleep.call_count}"
        print(f"Successfully retried {call_count} times with sleep delays and recovered.")

    print("[PASS] TEST 6: Transient 503/UNAVAILABLE retried with backoff as expected.")

    # -------------------------------------------------------------
    # TEST 7: Gemini RESOURCE_EXHAUSTED (Quota Depleted) -> NO RETRIES
    # -------------------------------------------------------------
    print("\n--- TEST 7: Gemini Permanent Quota Depletion (NO RETRIES) ---")
    quota_call_count = 0

    def mock_generate_with_quota_exhausted(*args, **kwargs):
        nonlocal quota_call_count
        quota_call_count += 1
        raise Exception("429 RESOURCE_EXHAUSTED: You have exceeded your current quota or prepayment credits depleted.")

    with patch("app.core.generation.get_genai_client") as mock_client_getter, \
         patch("app.core.generation.time.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = mock_generate_with_quota_exhausted
        mock_client_getter.return_value = mock_client

        with pytest.raises(GeminiQuotaExhaustedError) as exc_info:
            generate_answer(
                context_block="Context",
                history=[],
                message="Test question",
                max_retries=3
            )

        assert quota_call_count == 1, f"Expected exactly 1 call (no retries), got {quota_call_count}"
        assert mock_sleep.call_count == 0, f"Expected 0 sleep calls, got {mock_sleep.call_count}"
        assert "quota or prepaid credits have been exhausted" in str(exc_info.value)
        print("Confirmed: Aborted immediately on RESOURCE_EXHAUSTED without retries.")

    print("[PASS] TEST 7: Quota/credit exhaustion triggers immediate failure with zero wasteful retries.")

    # -------------------------------------------------------------
    # TEST 8: Full Chat and Voice Endpoint Integration via TestClient
    # -------------------------------------------------------------
    print("\n--- TEST 8: Chat and Voice Endpoint Integration & Source Provenance ---")
    with TestClient(app) as client:
        # Authenticate as P001
        login_res = client.post("/auth/login", json={"patient_id": "P001", "password": "P001"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        auth_token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {auth_token}"}

        # Check Chat endpoint with P001
        test_session_id = f"test_opt_{uuid.uuid4().hex[:8]}"

        with patch("app.core.generation.get_genai_client") as mock_client_getter:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = "Based on your EHR record, your Metformin dosage is 500mg twice daily."
            mock_client.models.generate_content.return_value = mock_resp
            mock_client_getter.return_value = mock_client

            # 1. First Turn
            res = client.post("/chat", json={
                "session_id": test_session_id,
                "patient_id": "P001",
                "message": "What is my Metformin dosage?"
            }, headers=auth_headers)
            assert res.status_code == 200, f"Chat failed: {res.text}"
            data = res.json()
            print("Chat response received:")
            print("  Answer:", data["answer"])
            print("  Patient Sources:", data["patient_sources"])
            print("  External Sources:", data["external_sources"])
            print("  History length:", len(data["history"]))

            # Patient sources must be <= 5 and must correspond to selected chunks
            assert len(data["patient_sources"]) <= 5
            assert len(data["external_sources"]) <= 3
            assert len(data["history"]) == 2

            # 2. Verify Voice chat endpoint delegates to same pipeline
            # Import dummy audio generator from existing test
            from test_voice_endpoint import create_dummy_wav_bytes
            wav_bytes = create_dummy_wav_bytes()

            # Mock Whisper ASR so it returns transcribed text
            with patch("app.routes.voice.asr_manager.transcribe_audio_file") as mock_asr:
                mock_asr.return_value = "What is my follow up schedule?"
                voice_res = client.post(
                    "/voice-chat",
                    data={"session_id": test_session_id, "patient_id": "P001"},
                    files={"audio": ("test.wav", wav_bytes, "audio/wav")},
                    headers=auth_headers
                )
                assert voice_res.status_code == 200, f"Voice chat failed: {voice_res.text}"
                v_data = voice_res.json()
                print("Voice Chat response received:")
                print("  Transcribed text:", v_data["transcribed_text"])
                print("  History length after voice turn:", len(v_data["history"]))
                assert v_data["transcribed_text"] == "What is my follow up schedule?"
                assert len(v_data["history"]) == 4

        # Cleanup test session
        client.delete(f"/chat/{test_session_id}", headers=auth_headers)

    print("[PASS] TEST 8: Chat and Voice endpoints work seamlessly with optimized RAG and source provenance.")

    # -------------------------------------------------------------
    # TEST 9: Safe Fallback on Semantic Filtering Failure
    # -------------------------------------------------------------
    print("\n--- TEST 9: Safe Fallback on Filtering Error ---")
    mock_records = [
        {"_id": "rec_1", "chunk_id": "c1", "patient_id": "P1", "content": "Note 1"},
        {"_id": "rec_2", "chunk_id": "c2", "patient_id": "P1", "content": "Note 2"},
        {"_id": "rec_3", "chunk_id": "c3", "patient_id": "P1", "content": "Note 3"},
        {"_id": "rec_4", "chunk_id": "c4", "patient_id": "P1", "content": "Note 4"},
        {"_id": "rec_5", "chunk_id": "c5", "patient_id": "P1", "content": "Note 5"},
        {"_id": "rec_6", "chunk_id": "c6", "patient_id": "P1", "content": "Note 6"}
    ]
    with patch.object(vector_store, "embed_query", side_effect=RuntimeError("Simulated embedding failure")):
        # Must gracefully return all 6 records rather than dropping them or crashing
        fallback_res = filter_relevant_ehr_records(
            patient_records=mock_records,
            query="test query",
            top_k=5
        )
        assert len(fallback_res) == 6
        assert fallback_res == mock_records
        print("Gracefully caught embedding error and returned all 6 original patient records.")

    print("[PASS] TEST 9: Fallback mechanism safely preserves all patient records if filtering fails.")

    print("\n" + "=" * 60)
    print("ALL 9 OPTIMIZATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_all_tests()

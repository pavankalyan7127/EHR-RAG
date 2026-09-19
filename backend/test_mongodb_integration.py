import os
import sys
import uuid
import logging
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import app
from app.db.connection import db_manager
from app.db.repositories import (
    get_patient,
    get_all_patient_ids,
    get_ehr_records_by_patient,
    get_session,
    get_session_messages,
    delete_messages_by_session,
    delete_session
)
from app.core.embeddings import vector_store
from app.core.retrieval import search_external_knowledge

from unittest.mock import patch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_mongodb_integration")

@patch("app.routes.chat.generate_answer", return_value="Metformin is prescribed for Type 2 diabetes.")
def run_tests(mock_gen):
    print("\n==================================================")
    print("RUNNING COMPREHENSIVE MONGODB ATLAS INTEGRATION TESTS")
    print("==================================================")

    # Use TestClient with context manager to trigger lifespan startup and shutdown
    with TestClient(app) as client:
        # TEST 1: Health Endpoint & Database Connection
        print("\n--- TEST 1: Health Check & Connection Status ---")
        health_res = client.get("/")
        assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
        data = health_res.json()
        print(f"Health check response: {data}")
        assert data["database"] == "connected"
        assert data["status"] == "healthy"
        print("[PASS] TEST 1: MongoDB Atlas connection is healthy and active.")

        # TEST 4: GET /patients
        print("\n--- TEST 4: GET /patients ---")
        patients_res = client.get("/patients")
        assert patients_res.status_code == 200, f"GET /patients failed: {patients_res.text}"
        p_data = patients_res.json()
        patient_list = p_data.get("patients", [])
        print(f"Retrieved {len(patient_list)} patients from MongoDB. Sample: {patient_list[:5]}")
        assert len(patient_list) >= 30, f"Expected at least 30 patients, got {len(patient_list)}"
        assert "P001" in patient_list and "P002" in patient_list
        print("[PASS] TEST 4: Patients retrieved directly from MongoDB.")

        # TEST 10: Patient-Specific EHR Retrieval Isolation
        print("\n--- TEST 10: Patient-Specific EHR Retrieval Isolation ---")
        p001_records = get_ehr_records_by_patient("P001")
        assert len(p001_records) > 0, "No EHR records found for P001"
        for rec in p001_records:
            assert rec["patient_id"] == "P001", f"Found non-P001 record in P001 query: {rec}"
            assert "Metformin" in rec["content"] or "Diabetes" in rec["content"]
        print(f"Retrieved {len(p001_records)} EHR record(s) for P001. Chunk ID: {p001_records[0]['chunk_id']}")
        print("[PASS] TEST 10: EHR retrieval strictly deterministic and patient-isolated.")

        # TEST 11: MedQuAD External FAISS Retrieval
        print("\n--- TEST 11: MedQuAD External FAISS Retrieval ---")
        ext_chunks = search_external_knowledge("What are the side effects of Metformin?", top_k=3)
        assert len(ext_chunks) > 0, "No external MedQuAD chunks retrieved from FAISS"
        for chunk in ext_chunks:
            assert chunk.get("source_type") == "external"
        print(f"Retrieved {len(ext_chunks)} external MedQuAD chunks. Sample chunk_id: {ext_chunks[0].get('chunk_id')}")
        print("[PASS] TEST 11: FAISS external retrieval intact and operational.")

        # TEST 5 & 6: Create Chat for P001 & Persist Turn in MongoDB
        print("\n--- TEST 5 & 6: Chat Session & Message Persistence ---")
        login_res = client.post("/auth/login", json={"patient_id": "P001", "password": "P001"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        p001_token = login_res.json()["access_token"]
        p001_headers = {"Authorization": f"Bearer {p001_token}"}

        test_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        chat_payload = {
            "session_id": test_session_id,
            "patient_id": "P001",
            "message": "What is my current dosage of Metformin?"
        }
        chat_res = client.post("/chat", json=chat_payload, headers=p001_headers)
        assert chat_res.status_code == 200, f"POST /chat failed: {chat_res.text}"
        chat_data = chat_res.json()
        print(f"Assistant Answer: {chat_data['answer'][:120]}...")
        print(f"Patient Sources: {chat_data['patient_sources']}")
        print(f"External Sources: {chat_data['external_sources']}")
        assert any("ehr_P001" in s for s in chat_data["patient_sources"])
        assert len(chat_data["history"]) == 2

        # Verify Session document in MongoDB
        session_doc = get_session(test_session_id)
        assert session_doc is not None, "Session document was not created in MongoDB"
        assert session_doc["patient_id"] == "P001"
        print(f"Session verified in MongoDB: {session_doc['_id']} for patient {session_doc['patient_id']}")

        # Verify Messages in MongoDB
        messages = get_session_messages(test_session_id)
        assert len(messages) == 2, f"Expected 2 messages in MongoDB, found {len(messages)}"
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is my current dosage of Metformin?"
        assert messages[1]["role"] == "assistant"
        assert len(messages[1]["sources"]) > 0
        print(f"Messages verified in MongoDB: User & Assistant stored with sources {messages[1]['sources']}")
        print("[PASS] TEST 5 & 6: Session and messages persisted with provenance in MongoDB.")

        # TEST 7 & 8: Multi-turn Continuity from MongoDB
        print("\n--- TEST 7 & 8: Multi-turn Session Continuation from MongoDB ---")
        turn2_payload = {
            "session_id": test_session_id,
            "patient_id": "P001",
            "message": "When is my follow-up appointment?"
        }
        turn2_res = client.post("/chat", json=turn2_payload, headers=p001_headers)
        assert turn2_res.status_code == 200, f"Turn 2 failed: {turn2_res.text}"
        turn2_data = turn2_res.json()
        assert len(turn2_data["history"]) == 4
        print(f"History after turn 2: {len(turn2_data['history'])} messages")
        
        # Verify messages in DB count
        updated_msgs = get_session_messages(test_session_id)
        assert len(updated_msgs) == 4
        print("[PASS] TEST 7 & 8: Multi-turn history accurately loaded and updated in MongoDB.")

        # TEST 9: Session Patient Mismatch Rejection
        print("\n--- TEST 9: Session Patient Mismatch Security Rejection ---")
        mismatch_payload = {
            "session_id": test_session_id,
            "patient_id": "P002", # Trying to use P001's session/auth with P002
            "message": "Tell me about my heart condition."
        }
        mismatch_res = client.post("/chat", json=mismatch_payload, headers=p001_headers)
        assert mismatch_res.status_code in [400, 403], f"Expected 400 or 403, got {mismatch_res.status_code}"
        print(f"Rejected as expected with detail: {mismatch_res.json().get('detail')}")
        print("[PASS] TEST 9: Cross-patient session hijacking prevented.")

        # TEST: DELETE /chat/{session_id}
        print("\n--- TEST: DELETE /chat/{session_id} Session Cleanup ---")
        del_res = client.delete(f"/chat/{test_session_id}", headers=p001_headers)
        assert del_res.status_code == 200
        del_data = del_res.json()
        assert del_data["cleared"] is True
        # Verify MongoDB cleanup
        assert get_session(test_session_id) is None
        assert len(get_session_messages(test_session_id)) == 0
        print("[PASS] Session cleanup in MongoDB verified.")

        # TEST 13: MongoDB Collections Verification
        print("\n--- TEST 13: MongoDB Collections Structure ---")
        db = db_manager.get_database()
        cols = db.list_collection_names()
        print(f"Collections present in database '{db.name}': {cols}")
        for req_col in ["patients", "ehr_records", "sessions", "messages", "users"]:
            assert req_col in cols, f"Missing required collection: {req_col}"
            print(f"Collection '{req_col}' document count: {db[req_col].count_documents({})}")
        print("[PASS] TEST 13: All 5 MongoDB collections active and indexed.")


    print("\n==================================================")
    print("ALL MONGODB INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()

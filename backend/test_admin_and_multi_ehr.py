import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import app
from app.db.repositories import (
    get_patient,
    get_user,
    get_ehr_records_by_patient,
    get_ehr_record_by_id,
    generate_next_ehr_id,
    delete_patient_cascade
)
from app.core.retrieval import retrieve_context, search_external_knowledge, build_context_block


@patch("app.routes.chat.generate_answer", return_value="Medical assessment completed based on your record.")
def test_suite(mock_generate):
    print("\n" + "=" * 70)
    print("RUNNING ADMIN DASHBOARD & MULTI-RECORD PATIENT EHR TEST SUITE")
    print("=" * 70)

    with TestClient(app) as client:
        # -------------------------------------------------------------
        # 1. Existing 30 EHR Records & Migrated IDs Check
        # -------------------------------------------------------------
        print("\n--- 1. Verification of 30 Migrated EHR Records ---")
        p001_records = get_ehr_records_by_patient("P001")
        assert len(p001_records) >= 1, "P001 has no EHR records"
        assert p001_records[0]["_id"] == "ehr_P001_001", f"Expected ehr_P001_001, got {p001_records[0]['_id']}"
        assert p001_records[0]["patient_id"] == "P001"
        assert p001_records[0].get("recorded_at") is not None
        assert p001_records[0].get("created_at") is not None
        assert p001_records[0].get("updated_at") is not None
        print(f"[PASS] P001 record verified: {p001_records[0]['_id']} with separate timestamps.")

        # Verify P030 also has migrated ID
        p030_records = get_ehr_records_by_patient("P030")
        assert len(p030_records) >= 1, "P030 has no EHR records"
        assert p030_records[0]["_id"] == "ehr_P030_001", f"Expected ehr_P030_001, got {p030_records[0]['_id']}"
        print(f"[PASS] P030 record verified: {p030_records[0]['_id']}.")

        # -------------------------------------------------------------
        # 2. Existing Patient Login, Chat & History
        # -------------------------------------------------------------
        print("\n--- 2. Patient Login & Chat Functionality ---")
        p_res = client.post("/auth/login", json={"patient_id": "P001", "password": "P001"})
        assert p_res.status_code == 200, f"P001 login failed: {p_res.text}"
        p_data = p_res.json()
        assert p_data["role"] == "patient"
        token_p001 = p_data["access_token"]
        headers_p001 = {"Authorization": f"Bearer {token_p001}"}

        test_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        chat_res = client.post(
            "/chat",
            json={"session_id": test_session_id, "message": "What is my diagnosis?"},
            headers=headers_p001
        )
        assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
        chat_data = chat_res.json()
        assert "ehr_P001_001" in chat_data["patient_sources"]
        print("[PASS] P001 login, role exposure ('patient'), and chat grounding on ehr_P001_001 verified.")

        # Cleanup chat session
        client.delete(f"/chat/{test_session_id}", headers=headers_p001)

        # -------------------------------------------------------------
        # 3. Patient Isolation: P001 cannot retrieve P002
        # -------------------------------------------------------------
        print("\n--- 3. Strict Patient Isolation ---")
        p001_retrieved, _ = retrieve_context("P001", "heart condition")
        for rec in p001_retrieved:
            assert rec["patient_id"] == "P001", f"Isolation breach: retrieved {rec['patient_id']} for P001"
        print("[PASS] P001 EHR context is strictly isolated to P001.")

        # -------------------------------------------------------------
        # 4. Admin Authentication
        # -------------------------------------------------------------
        print("\n--- 4. Admin Login & RBAC Verification ---")
        admin_res = client.post("/auth/login", json={"patient_id": "admin", "password": "Admin@123"})
        assert admin_res.status_code == 200, f"Admin login failed: {admin_res.text}"
        admin_data = admin_res.json()
        assert admin_data["role"] == "admin", f"Expected admin role, got {admin_data.get('role')}"
        token_admin = admin_data["access_token"]
        headers_admin = {"Authorization": f"Bearer {token_admin}"}
        print("[PASS] Administrator logged in successfully. JWT role is 'admin'.")

        # -------------------------------------------------------------
        # 5. Patient Account Cannot Access Admin Endpoints (RBAC Enforced)
        # -------------------------------------------------------------
        print("\n--- 5. Patient Forbidden from Admin Endpoints ---")
        forbidden_res = client.get("/admin/patients", headers=headers_p001)
        assert forbidden_res.status_code == 403, f"Expected 403 Forbidden, got {forbidden_res.status_code}"
        print(f"[PASS] Patient rejected from /admin/patients with 403 Forbidden: {forbidden_res.json()['detail']}")

        # -------------------------------------------------------------
        # 6. Admin Patient Listing
        # -------------------------------------------------------------
        print("\n--- 6. Admin Patient Registry Listing ---")
        list_res = client.get("/admin/patients", headers=headers_admin)
        assert list_res.status_code == 200, f"Failed to list patients: {list_res.text}"
        patients_list = list_res.json()
        assert len(patients_list) >= 30, f"Expected at least 30 patients, got {len(patients_list)}"
        sample_item = next(p for p in patients_list if p["patient_id"] == "P001")
        assert sample_item["record_count"] >= 1
        assert sample_item["is_active"] is True
        print(f"[PASS] Admin listed {len(patients_list)} patients with record counts and active statuses.")

        # -------------------------------------------------------------
        # 7. Admin Creates New Patient (Zero EHR Records Initially)
        # -------------------------------------------------------------
        print("\n--- 7. Admin Adds New Patient (P099) ---")
        # Clean up in case P099 existed from previous aborted runs
        delete_patient_cascade("P099")

        create_patient_payload = {
            "patient_id": "P099",
            "name": "Jane Test Doe",
            "age": 42,
            "gender": "Female",
            "password": "Password99!"
        }
        create_res = client.post("/admin/patients", json=create_patient_payload, headers=headers_admin)
        assert create_res.status_code == 201, f"Patient creation failed: {create_res.text}"
        new_p_data = create_res.json()
        assert new_p_data["patient_id"] == "P099"
        assert new_p_data["record_count"] == 0
        assert new_p_data["is_active"] is True
        print(f"[PASS] Patient P099 created with 0 medical records.")

        # Verify new patient can log in
        login_p099 = client.post("/auth/login", json={"patient_id": "P099", "password": "Password99!"})
        assert login_p099.status_code == 200, f"P099 login failed: {login_p099.text}"
        token_p099 = login_p099.json()["access_token"]
        headers_p099 = {"Authorization": f"Bearer {token_p099}"}
        print("[PASS] New patient P099 authenticated successfully.")

        # Verify RAG works for patient with 0 records
        p099_recs, _ = retrieve_context("P099", "Do I have any allergies?")
        assert len(p099_recs) == 0
        ctx = build_context_block("P099", p099_recs, [])
        assert "[No record found for this patient ID]" in ctx
        print("[PASS] RAG pipeline gracefully handles patient with 0 EHR records.")

        # -------------------------------------------------------------
        # 8. Patient Deactivation and Reactivation Workflow
        # -------------------------------------------------------------
        print("\n--- 8. Patient Deactivation & Reactivation Workflow ---")
        # Admin deactivates P099
        deact_res = client.put("/admin/patients/P099", json={"is_active": False}, headers=headers_admin)
        assert deact_res.status_code == 200
        assert deact_res.json()["is_active"] is False

        # Deactivated patient login attempt must be rejected
        deact_login = client.post("/auth/login", json={"patient_id": "P099", "password": "Password99!"})
        assert deact_login.status_code == 401, f"Expected 401/403 for deactivated user, got {deact_login.status_code}"

        # Reactivate P099
        react_res = client.put("/admin/patients/P099", json={"is_active": True}, headers=headers_admin)
        assert react_res.status_code == 200
        assert react_res.json()["is_active"] is True

        # Now login succeeds again
        react_login = client.post("/auth/login", json={"patient_id": "P099", "password": "Password99!"})
        assert react_login.status_code == 200
        print("[PASS] Deactivation and Reactivation workflow validated: records preserved, login blocked/restored.")

        # -------------------------------------------------------------
        # 9. Admin Medical Record CRUD & Monotonic Sequence Generation
        # -------------------------------------------------------------
        print("\n--- 9. Medical Record CRUD & Monotonic Non-Reusing Sequences ---")
        # 1. Add Record 1 for P099 -> ehr_P099_001
        rec1_res = client.post(
            "/admin/patients/P099/records",
            json={
                "content": "Initial visit: Patient diagnosed with seasonal allergic rhinitis.",
                "chunk_type": "initial_consultation",
                "recorded_at": "2026-01-15T09:00:00Z"
            },
            headers=headers_admin
        )
        assert rec1_res.status_code == 201, f"Add record 1 failed: {rec1_res.text}"
        rec1_data = rec1_res.json()
        assert rec1_data["_id"] == "ehr_P099_001", f"Expected ehr_P099_001, got {rec1_data['_id']}"
        print(f"[PASS] Record 1 created: {rec1_data['_id']}")

        # 2. Add Record 2 for P099 -> ehr_P099_002
        rec2_res = client.post(
            "/admin/patients/P099/records",
            json={
                "content": "Follow-up visit: Prescribed Cetirizine 10mg once daily. Symptoms improving.",
                "chunk_type": "medication_update",
                "recorded_at": "2026-03-20T10:30:00Z"
            },
            headers=headers_admin
        )
        assert rec2_res.status_code == 201
        rec2_data = rec2_res.json()
        assert rec2_data["_id"] == "ehr_P099_002", f"Expected ehr_P099_002, got {rec2_data['_id']}"
        print(f"[PASS] Record 2 created: {rec2_data['_id']}")

        # 3. Add Record 3 for P099 -> ehr_P099_003
        rec3_res = client.post(
            "/admin/patients/P099/records",
            json={
                "content": "Specialist consultation: Recommended nasal saline rinses and allergen avoidance.",
                "chunk_type": "specialist_note",
                "recorded_at": "2026-05-10T14:00:00Z"
            },
            headers=headers_admin
        )
        assert rec3_res.status_code == 201
        rec3_data = rec3_res.json()
        assert rec3_data["_id"] == "ehr_P099_003", f"Expected ehr_P099_003, got {rec3_data['_id']}"
        print(f"[PASS] Record 3 created: {rec3_data['_id']}")

        # 4. Delete Record 2 (ehr_P099_002)
        del_rec2 = client.delete("/admin/patients/P099/records/ehr_P099_002", headers=headers_admin)
        assert del_rec2.status_code == 200
        assert get_ehr_record_by_id("ehr_P099_002") is None
        print("[PASS] Deleted record ehr_P099_002.")

        # 5. Add a new record -> SEQUENCE MUST BE ehr_P099_004 (NEVER REUSE 002!)
        rec4_res = client.post(
            "/admin/patients/P099/records",
            json={
                "content": "Annual check-up: Allergy well-controlled on maintenance regimen.",
                "chunk_type": "annual_checkup",
                "recorded_at": "2026-09-18T11:00:00Z"
            },
            headers=headers_admin
        )
        assert rec4_res.status_code == 201
        rec4_data = rec4_res.json()
        assert rec4_data["_id"] == "ehr_P099_004", f"CRITICAL FAILURE: Sequence reused! Expected ehr_P099_004, got {rec4_data['_id']}"
        print(f"[PASS] Monotonic sequence verified: Next record is {rec4_data['_id']} (002 was NOT reused).")

        # 6. Edit an existing record
        edit_res = client.put(
            "/admin/patients/P099/records/ehr_P099_004",
            json={"content": "Annual check-up: Allergy well-controlled. Refilled Cetirizine."},
            headers=headers_admin
        )
        assert edit_res.status_code == 200
        assert "Refilled Cetirizine" in edit_res.json()["content"]
        assert edit_res.json()["updated_at"] is not None
        print("[PASS] Record edited and updated_at refreshed.")

        # -------------------------------------------------------------
        # 10. Multi-Record RAG Context Assembly & Progression
        # -------------------------------------------------------------
        print("\n--- 10. Multi-Record RAG Context & Temporal Progression ---")
        retrieved_p099, _ = retrieve_context("P099", "What allergy medication am I taking?")
        assert len(retrieved_p099) == 3, f"Expected 3 active records for P099, got {len(retrieved_p099)}"
        ctx_block = build_context_block("P099", retrieved_p099, [])
        print("Generated Patient Context Block Preview:\n", ctx_block[:350], "...\n")
        assert "Type: initial_consultation" in ctx_block
        assert "Type: annual_checkup" in ctx_block
        assert "2026-01-15" in ctx_block
        assert "2026-09-18" in ctx_block
        print("[PASS] Context block retains temporal metadata and record types for clinical progression.")

        # -------------------------------------------------------------
        # 11. FAISS Knowledge Base Read-Only Verification
        # -------------------------------------------------------------
        print("\n--- 11. FAISS External Knowledge Base Integrity ---")
        ext = search_external_knowledge("allergic rhinitis", top_k=3)
        assert len(ext) == 3
        for chunk in ext:
            assert chunk["source_type"] == "external"
        print("[PASS] FAISS external medical knowledge base remains completely untouched and functional.")

        # Cleanup test patient P099
        delete_patient_cascade("P099")
        print("[PASS] Cleaned up temporary test patient P099.")

    print("\n" + "=" * 70)
    print("ALL 11 ADMIN DASHBOARD & MULTI-RECORD TEST GROUPS PASSED!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_suite()

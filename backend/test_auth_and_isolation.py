import sys
import uuid
from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import app
from app.db.repositories import (
    get_user,
    get_session,
    get_session_messages
)

@patch("app.routes.chat.generate_answer", return_value="Your medication Metformin 500mg is prescribed twice daily.")
def run_tests(mock_gen):
    print("\n========================================================")
    print("RUNNING PATIENT AUTH & PATIENT ISOLATION VERIFICATION SUITE")
    print("========================================================")

    with TestClient(app) as client:
        # TEST 1: Valid Login for P017
        print("\n--- TEST 1: Valid Login (P017 / P017) ---")
        login_res = client.post("/auth/login", json={"patient_id": "P017", "password": "P017"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        data_p017 = login_res.json()
        assert "access_token" in data_p017
        assert data_p017["patient_id"] == "P017"
        assert data_p017["token_type"] == "bearer"
        token_p017 = data_p017["access_token"]
        headers_p017 = {"Authorization": f"Bearer {token_p017}"}
        print(f"[PASS] TEST 1: P017 logged in successfully. Token: {token_p017[:25]}...")

        # TEST 2: Invalid Password
        print("\n--- TEST 2: Invalid Password (P017 / WRONG) ---")
        bad_pwd_res = client.post("/auth/login", json={"patient_id": "P017", "password": "WRONG_PASSWORD"})
        assert bad_pwd_res.status_code == 401, f"Expected 401, got {bad_pwd_res.status_code}"
        assert bad_pwd_res.json()["detail"] == "Invalid patient ID or password."
        print("[PASS] TEST 2: Invalid password correctly rejected with generic error.")

        # TEST 3: Unknown Patient
        print("\n--- TEST 3: Unknown Patient (P999 / P999) ---")
        unknown_res = client.post("/auth/login", json={"patient_id": "P999", "password": "P999"})
        assert unknown_res.status_code == 401, f"Expected 401, got {unknown_res.status_code}"
        assert unknown_res.json()["detail"] == "Invalid patient ID or password."
        print("[PASS] TEST 3: Unknown patient correctly rejected with generic error.")

        # TEST 4: Get Current Patient Profile
        print("\n--- TEST 4: GET /patients/me for P017 ---")
        profile_res = client.get("/patients/me", headers=headers_p017)
        assert profile_res.status_code == 200, f"Profile failed: {profile_res.text}"
        prof = profile_res.json()
        assert prof["patient_id"] == "P017"
        print(f"[PASS] TEST 4: Retrieved profile for {prof['patient_id']} ({prof['name']}).")

        # TEST 5: Create Chat Session for P017
        print("\n--- TEST 5: Create Chat Session for P017 ---")
        create_sess_res = client.post("/chat/sessions", json={"title": "Blood Pressure Discussion"}, headers=headers_p017)
        assert create_sess_res.status_code == 200, f"Create session failed: {create_sess_res.text}"
        sess_data = create_sess_res.json()
        sess_id = sess_data["session_id"]
        assert sess_data["patient_id"] == "P017"
        assert sess_data["title"] == "Blood Pressure Discussion"
        print(f"[PASS] TEST 5: Session {sess_id} created for patient P017.")

        # TEST 6: Unauthenticated Request Rejection
        print("\n--- TEST 6: Unauthenticated Request Rejection ---")
        unauth_res = client.get("/chat/sessions")
        assert unauth_res.status_code == 401, f"Expected 401, got {unauth_res.status_code}"
        print("[PASS] TEST 6: Unauthenticated access to /chat/sessions correctly rejected.")

        # TEST 7: Authenticated Chat with P017
        print("\n--- TEST 7: Authenticated Chat with P017 ---")
        chat_payload = {
            "session_id": sess_id,
            "message": "What is my current dosage of medication?"
        }
        chat_res = client.post("/chat", json=chat_payload, headers=headers_p017)
        assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
        chat_data = chat_res.json()
        print(f"Assistant Answer: {chat_data['answer'][:100]}...")
        assert len(chat_data["history"]) == 2
        print("[PASS] TEST 7: Chat query processed and recorded for P017.")

        # TEST 8: Cross-Patient Data Access Prevention
        print("\n--- TEST 8: Cross-Patient Spoofing Attempt Rejected ---")
        # P017 attempts to pass patient_id="P018" in ChatRequest
        spoof_payload = {
            "session_id": f"sess_{uuid.uuid4().hex[:8]}",
            "patient_id": "P018",
            "message": "Give me P018 records"
        }
        spoof_res = client.post("/chat", json=spoof_payload, headers=headers_p017)
        assert spoof_res.status_code == 403, f"Expected 403 Forbidden, got {spoof_res.status_code}"
        print(f"[PASS] TEST 8: Spoofing attempt blocked: {spoof_res.json()['detail']}")

        # TEST 9: Login as P018 and Verify Session Isolation
        print("\n--- TEST 9: Login as P018 and Verify Session Isolation ---")
        login_p018 = client.post("/auth/login", json={"patient_id": "P018", "password": "P018"})
        assert login_p018.status_code == 200
        token_p018 = login_p018.json()["access_token"]
        headers_p018 = {"Authorization": f"Bearer {token_p018}"}

        # P018 lists sessions: should NOT see P017's session
        p018_sessions_res = client.get("/chat/sessions", headers=headers_p018)
        assert p018_sessions_res.status_code == 200
        p018_sessions = p018_sessions_res.json()
        p018_session_ids = [s["session_id"] for s in p018_sessions]
        assert sess_id not in p018_session_ids, f"Security Breach: P018 can see P017 session {sess_id}"
        print(f"[PASS] TEST 9: P017 session {sess_id} is NOT visible in P018 session list.")

        # TEST 10: P018 Direct Access to P017 Session Rejected
        print("\n--- TEST 10: P018 Direct Access to P017 Session Rejected ---")
        leak_res = client.get(f"/chat/sessions/{sess_id}", headers=headers_p018)
        assert leak_res.status_code == 404, f"Expected 404, got {leak_res.status_code}"
        print("[PASS] TEST 10: P018 cannot access P017 session details (returned 404).")

        # TEST 11: P017 Retrieves Own Session Details
        print("\n--- TEST 11: P017 Retrieves Own Session Details ---")
        own_sess_res = client.get(f"/chat/sessions/{sess_id}", headers=headers_p017)
        assert own_sess_res.status_code == 200
        own_data = own_sess_res.json()
        assert own_data["session_id"] == sess_id
        assert len(own_data["messages"]) == 2
        print(f"[PASS] TEST 11: P017 successfully loaded own session messages ({len(own_data['messages'])} messages).")

        # TEST 12: Continue Existing Session (Multi-turn)
        print("\n--- TEST 12: Continue Existing Session (Multi-turn) ---")
        turn2_payload = {
            "session_id": sess_id,
            "message": "Can you elaborate on any potential side effects?"
        }
        turn2_res = client.post("/chat", json=turn2_payload, headers=headers_p017)
        assert turn2_res.status_code == 200
        assert len(turn2_res.json()["history"]) == 4

        reloaded = client.get(f"/chat/sessions/{sess_id}", headers=headers_p017).json()
        assert len(reloaded["messages"]) == 4
        print("[PASS] TEST 12: Conversation continued in same session. 4 messages persisted in MongoDB.")

        # TEST 13: Delete Session
        print("\n--- TEST 13: Delete Session for P017 ---")
        del_res = client.delete(f"/chat/sessions/{sess_id}", headers=headers_p017)
        assert del_res.status_code == 200
        assert del_res.json()["cleared"] is True
        # Verify it no longer exists
        assert client.get(f"/chat/sessions/{sess_id}", headers=headers_p017).status_code == 404
        print("[PASS] TEST 13: Session deleted cleanly.")

    print("\n========================================================")
    print("ALL PATIENT AUTH & ISOLATION TESTS PASSED SUCCESSFULLY!")
    print("========================================================")

if __name__ == "__main__":
    run_tests()

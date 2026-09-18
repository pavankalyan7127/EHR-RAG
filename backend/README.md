# Multimodal RAG Assistant for Personalized Question Answering over EHRs (Backend)

A production-style FastAPI backend service implementing multimodal personalized question answering over Electronic Health Records (EHRs) and external medical knowledge bases (MedQuAD) using Retrieval-Augmented Generation (RAG), **MongoDB Atlas** for persistent operational storage, Google Gemini (`gemini-2.5-flash`), FAISS, `all-MiniLM-L6-v2`, and OpenAI Whisper.

---

## 🏗 System Architecture & Key Design Decisions

```
Frontend (React)
    ↓
FastAPI Backend
    ├── [Track 1] MongoDB Atlas Persistence
    │       ├── patients (Demographics, IDs, metadata)
    │       ├── ehr_records (Clinical notes, strictly deterministic by patient_id)
    │       ├── sessions (Multi-turn session tracking & patient ownership)
    │       └── messages (Chronological user & assistant turns with source provenance)
    │
    ├── [Track 2] FAISS Index + chunk_metadata.json
    │       └── MedQuAD semantic vector retrieval (top-k external medical chunks)
    │
    ├── Dual-Track Context Assembly (EHR context + MedQuAD reference context + Chat history)
    ↓
Google Gemini 2.5/3.x Flash (Grounded generation with strict citations)
```

### 1. Dual-Track Hybrid Retrieval: MongoDB Patient EHR vs FAISS Semantic Search
- **Track 1 (Deterministic Patient EHR):** To eliminate privacy risk and guarantee 100% accurate patient context (avoiding semantic mismatch or cross-patient vector leakage), patient EHR notes are queried directly from MongoDB's `ehr_records` collection filtered strictly by `patient_id`.
- **Track 2 (External MedQuAD Knowledge):** General medical reference knowledge is retrieved semantically using SentenceTransformers (`all-MiniLM-L6-v2`) and FAISS (L2 Index).

### 2. Multi-Turn Session & History Persistence in MongoDB
- Sessions and messages are persistently stored in MongoDB across backend restarts.
- Individual message documents are stored separately with `session_id` and timestamps (preventing unbounded document growth).
- **Patient Security Isolation:** Sessions are strictly bound to a single `patient_id`. If a session created for patient `P001` is accessed with `patient_id: "P002"`, the request is rejected with a `400 Bad Request`.

### 3. Strict Anti-Hallucination & Provenance Instructions
- Gemini is configured with a strict system instruction to cite whether information comes from the **Patient's EHR note**, **External Medical Knowledge**, or **both**, and to state when information is insufficient rather than guessing.
- Conversation history is explicitly designated as **conversational flow context only** and is **never used as factual grounding**.

---

## 📁 Directory Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entry point, lifespan, CORS, health check
│   ├── config.py                # Environment variables and configuration settings
│   ├── db/
│   │   ├── __init__.py          # Database package
│   │   ├── connection.py        # MongoDBManager singleton, connection pooling, safe logging
│   │   ├── collections.py       # Central collection accessors
│   │   └── repositories.py      # CRUD repository layer for MongoDB
│   ├── data/
│   │   ├── chunk_metadata.json  # Chunk metadata array (EHR + external chunks)
│   │   └── faiss_index.bin      # Pre-built FAISS IndexFlatL2 index
│   ├── core/
│   │   ├── embeddings.py        # SentenceTransformer & FAISS vector store manager
│   │   ├── retrieval.py         # Dual-track retrieval (MongoDB EHR + FAISS MedQuAD)
│   │   ├── generation.py        # Prompt construction & Google GenAI (Gemini) client with retry
│   │   └── asr.py               # OpenAI Whisper speech-to-text loader and transcriber
│   ├── chat/
│   │   └── session_manager.py   # MongoDB-backed multi-turn session and message manager
│   ├── models/
│   │   └── schemas.py           # Pydantic models for MongoDB documents & API schemas
│   └── routes/
│       ├── chat.py              # POST /chat and DELETE /chat/{session_id}
│       ├── voice.py             # POST /voice-chat (Multipart audio upload)
│       └── patients.py          # GET /patients (Retrieved from MongoDB)
├── seed_database.py             # Idempotent database seeding script
├── run.py                       # Startup script (starts server on port 8000 with reload)
├── test_mongodb_integration.py  # Integration test suite
├── test_voice_endpoint.py       # Voice endpoint test suite
├── requirements.txt             # Pinned project dependencies
├── .env.example                 # Environment configuration template
└── README.md                    # Setup and usage guide
```

---

## 🗄 MongoDB Atlas Collections Schema

### 1. `patients`
```json
{
  "_id": "P001",
  "name": "Patient P001",
  "age": 58,
  "gender": "Male",
  "created_at": "2026-09-18T10:14:51.700Z"
}
```

### 2. `ehr_records`
```json
{
  "_id": "ehr_P001",
  "patient_id": "P001",
  "chunk_id": "ehr_P001",
  "chunk_type": "clinical_note",
  "content": "Patient is a 58-year-old male with a history of Type 2 Diabetes Mellitus...",
  "metadata": {
    "source": "EHR",
    "source_type": "ehr"
  },
  "created_at": "2026-09-18T10:14:51.700Z"
}
```

### 3. `sessions`
```json
{
  "_id": "c11a4c9c-b26a-4d2a-a92c-5541e261e47d",
  "patient_id": "P001",
  "created_at": "2026-09-18T10:17:23.423Z",
  "updated_at": "2026-09-18T10:17:47.931Z",
  "status": "active"
}
```

### 4. `messages`
```json
{
  "_id": "msg_90e791e2b69446d78709e99a4c0eb3ff",
  "session_id": "c11a4c9c-b26a-4d2a-a92c-5541e261e47d",
  "patient_id": "P001",
  "role": "assistant",
  "content": "Based on your Patient EHR Record, your Metformin dosage was increased to 1000mg twice daily...",
  "timestamp": "2026-09-18T10:17:29.478Z",
  "sources": ["ehr_P001"]
}
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- A **MongoDB Atlas Cluster** connection URI
- A **Google Gemini API Key** ([Google AI Studio](https://aistudio.google.com/))
- (Optional for Whisper) `ffmpeg` installed on your system if uploading diverse audio container formats.

### 2. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in `backend/`:

```bash
cp .env.example .env
```

Edit `backend/.env`:
```env
# MongoDB Atlas Connection
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=ehr_rag_db

# Google Gemini API Key
GEMINI_API_KEY=AIzaSy...your_actual_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash

# Model Names
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
WHISPER_MODEL_NAME=base

# Allowed CORS Origins (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# Server Settings
HOST=0.0.0.0
PORT=8000
```

### 4. Seed the Database
Run the idempotent seeding script to populate MongoDB with synthetic patients and EHR clinical records:

```bash
# From the backend directory:
python seed_database.py

# Or from workspace root:
python backend/seed_database.py
```
> **Idempotency Note:** The seed script uses `replace_one` upserts, making it safe to run multiple times without creating duplicate records.

---

## 🏃 Running the Backend Server

1. Open a terminal.
2. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```
3. Run the startup script:
   ```bash
   python run.py
   ```
4. The backend will start on **port 8000** (with auto-reload enabled).

*(Equivalent to running `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`)*

Once running, interactive API documentation is available at:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Running Integration Tests

To run the automated MongoDB Atlas integration tests:

```bash
python backend/test_mongodb_integration.py
```

---

## 🧪 API Endpoints

### 1. Health Check (`GET /`)
```bash
curl -X GET http://localhost:8000/
```
**Response:**
```json
{
  "status": "healthy",
  "service": "Multimodal EHR RAG Assistant API",
  "database": "connected",
  "external_chunks": 609
}
```

### 2. List Available Patients (`GET /patients`)
```bash
curl -X GET http://localhost:8000/patients
```
**Response:**
```json
{
  "patients": ["P001", "P002", "P003", "..."]
}
```

### 3. Multi-Turn Chat (`POST /chat`)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_uuid_101",
    "patient_id": "P001",
    "message": "What is my current dosage of Metformin?"
  }'
```

### 4. Multimodal Voice Chat (`POST /voice-chat`)
```bash
curl -X POST http://localhost:8000/voice-chat \
  -F "session_id=sess_uuid_101" \
  -F "patient_id=P001" \
  -F "audio=@sample_query.wav"
```

### 5. Clear Session History (`DELETE /chat/{session_id}`)
```bash
curl -X DELETE http://localhost:8000/chat/sess_uuid_101
```

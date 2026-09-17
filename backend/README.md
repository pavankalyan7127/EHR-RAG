# Multimodal RAG Assistant for Personalized Question Answering over EHRs (Backend)

A production-style FastAPI backend service implementing multimodal personalized question answering over Electronic Health Records (EHRs) and external medical knowledge bases (MedQuAD) using Retrieval-Augmented Generation (RAG), Google Gemini (`gemini-2.5-flash`), FAISS, `all-MiniLM-L6-v2`, and OpenAI Whisper.

---

## 🏗 System Architecture & Key Design Decisions

### 1. Guaranteed Direct Patient Lookup vs FAISS Semantic Search
- **The Problem:** In purely semantic retrieval, searching a patient's own EHR with arbitrary patient questions often fails (e.g., asking *"Do I have any allergies?"* against an EHR note that never mentions allergy words might fail to retrieve the note via similarity scoring).
- **The Solution:** We maintain a direct hash map (`patient_id -> ehr_chunk`). Whenever a query is made with a `patient_id`, that patient's exact EHR note is **guaranteed** to be retrieved and injected into the context block.
- **External Knowledge Base:** Semantic similarity search with FAISS (L2 index) is reserved strictly for retrieving the top-3 relevant general medical knowledge chunks from MedQuAD.

### 2. Multi-Turn Conversation Grounding
- Conversation history is maintained per `session_id` to enable natural follow-up queries (e.g., *"What about the dosage?"*).
- The prompt sent to Gemini explicitly instructs the model that **conversation history is for conversational flow only** and **must NOT be treated as a source of verified medical facts**. Only the **Retrieved Medical Context** serves as the factual grounding.

### 3. Strict Anti-Hallucination & Provenance Instructions
- Gemini is configured with a strict system instruction to cite whether information comes from the **Patient's EHR note**, **External Medical Knowledge**, or **both**, and to state when information is insufficient rather than guessing.

---

## 📁 Directory Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entry point, lifespan, CORS
│   ├── config.py                # Environment variables and path settings
│   ├── data/
│   │   ├── chunk_metadata.json  # Chunk metadata array (EHR + external chunks)
│   │   └── faiss_index.bin      # Pre-built FAISS IndexFlatL2 index
│   ├── core/
│   │   ├── embeddings.py        # SentenceTransformer, FAISS loader, direct patient lookup
│   │   ├── retrieval.py         # Context retrieval (direct lookup + FAISS search)
│   │   ├── generation.py        # Prompt construction & Google GenAI (Gemini) client
│   │   └── asr.py               # OpenAI Whisper speech-to-text loader and transcriber
│   ├── chat/
│   │   └── session_manager.py   # In-memory multi-turn session store
│   ├── models/
│   │   └── schemas.py           # Pydantic request & response models
│   └── routes/
│       ├── chat.py              # POST /chat and DELETE /chat/{session_id}
│       ├── voice.py             # POST /voice-chat (Multipart audio upload)
│       └── patients.py          # GET /patients
├── requirements.txt             # Pinned project dependencies
├── .env.example                 # Environment configuration template
└── README.md                    # Setup and usage guide
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- A Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/))
- (Optional for Whisper) `ffmpeg` installed on your system if uploading diverse audio container formats.

### 2. Create Virtual Environment
Open a terminal in the project directory:

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in `backend/` from the template:

```bash
cp .env.example .env
```

Edit `backend/.env`:
```env
GEMINI_API_KEY=AIzaSy...your_actual_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
WHISPER_MODEL_NAME=base
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173
HOST=0.0.0.0
PORT=8000
```

### 5. Generate or Place Index & Data Files
If you are running the backend with placeholder/mock data first, run the mock generator from the root workspace:

```bash
# From workspace root (with venv activated)
python generate_mock_data.py
```
This generates `backend/app/data/chunk_metadata.json` and `backend/app/data/faiss_index.bin`.

> **Note for Real Colab Data:**
> When you're ready to use your real validated data from Google Colab, simply copy your 30 EHR + 579 external `chunk_metadata.json` and `faiss_index.bin` files directly into `backend/app/data/`. No code changes are required!

---

## 🏃 Running the Server

Start the FastAPI application using Uvicorn:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running, interactive API documentation is available at:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 API Testing Examples (`curl`)

### 1. List Available Patients (`GET /patients`)
```bash
curl -X GET http://localhost:8000/patients
```
**Response:**
```json
{
  "patients": ["P001", "P002", "P003"]
}
```

---

### 2. Multi-Turn Chat (`POST /chat`)
**Turn 1: Asking about medications and condition**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_101",
    "patient_id": "P001",
    "message": "What medications am I currently taking for my diabetes?"
  }'
```

**Response:**
```json
{
  "session_id": "session_101",
  "answer": "According to your personal EHR record, you are currently prescribed Metformin 1000 mg PO BID for Type 2 Diabetes Mellitus...",
  "patient_sources": ["ehr_P001"],
  "external_sources": ["ext_41", "ext_42"],
  "history": [
    {
      "role": "user",
      "content": "What medications am I currently taking for my diabetes?"
    },
    {
      "role": "assistant",
      "content": "According to your personal EHR record..."
    }
  ]
}
```

**Turn 2: Contextual follow-up using the same `session_id`**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_101",
    "patient_id": "P001",
    "message": "What is the dosage and do I have any allergies?"
  }'
```

---

### 3. Multimodal Voice Chat (`POST /voice-chat`)
Upload a recorded audio question (e.g. `.wav`, `.mp3`, `.m4a`):

```bash
curl -X POST http://localhost:8000/voice-chat \
  -F "session_id=session_101" \
  -F "patient_id=P001" \
  -F "audio=@sample_query.wav"
```

**Response:**
```json
{
  "session_id": "session_101",
  "transcribed_text": "What medications am I taking for my diabetes?",
  "answer": "Based on your EHR note...",
  "patient_sources": ["ehr_P001"],
  "external_sources": ["ext_41"],
  "history": [...]
}
```

---

### 4. Clear Session History (`DELETE /chat/{session_id}`)
```bash
curl -X DELETE http://localhost:8000/chat/session_101
```

**Response:**
```json
{
  "session_id": "session_101",
  "message": "Session history cleared successfully.",
  "cleared": true
}
```

---

### 5. Health Check (`GET /`)
```bash
curl -X GET http://localhost:8000/
```

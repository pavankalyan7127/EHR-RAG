# Multimodal EHR RAG Assistant - Frontend (React + Vite)

A modern, responsive React web interface designed for personalized medical question answering over Electronic Health Records (EHRs) and external medical knowledge bases (MedQuAD). 

The frontend connects over HTTP to the FastAPI backend service (`http://localhost:8000`) and supports continuous multi-turn text and voice conversations.

---

## ✨ Key Features

1. **Continuous Multi-Turn Dialogue:**
   - Conversation history is preserved across turns using a unique `session_id`.
   - Messages are smoothly appended in an auto-scrolling chat window (ChatGPT style).

2. **Patient Selector:**
   - Dynamically loads registered patients from `GET /patients`.
   - Selecting a new patient automatically resets the chat session and clears previous conversation context.

3. **Multimodal Input Support:**
   - **Typed Queries:** Send messages with the Enter key or Send button.
   - **Live Audio Recording:** Record voice queries using the browser microphone via the MediaRecorder API.
   - **Audio File Upload:** Upload audio files (`.wav`, `.mp3`, `.m4a`, etc.) for Whisper speech-to-text processing.

4. **Grounded Source Attribution:**
   - Every assistant response includes collapsible citation chips for the **Patient EHR Record** (`ehr_P001`) and **External Medical Knowledge Chunks** (`ext_41`, etc.) for auditability and anti-hallucination verification.

5. **Start New Chat:**
   - Resets the local message stream and calls `DELETE /chat/{session_id}` on the backend to clear server-side memory.

---

## 📁 Directory Structure

```
frontend/
├── public/
├── src/
│   ├── main.jsx                 # React entry point
│   ├── App.jsx                  # Main application layout and state coordination
│   ├── api/
│   │   └── client.js            # Encapsulated fetch API client for backend endpoints
│   ├── components/
│   │   ├── PatientSelector.jsx  # Top bar with patient dropdown & new chat button
│   │   ├── ChatWindow.jsx       # Scrollable message container with empty state
│   │   ├── MessageBubble.jsx    # User & assistant bubbles with citation dropdowns
│   │   └── InputBar.jsx         # Text input, microphone recorder, and file picker
│   ├── hooks/
│   │   └── useChat.js           # Multi-turn session manager hook & optimistic updates
│   └── styles/
│       └── App.css              # Clean, professional clinical styling
├── index.html                   # HTML template
├── package.json                 # Dependencies and npm scripts
├── vite.config.js               # Vite build and dev server configuration
└── .env.example                 # VITE_API_BASE_URL configuration template
```

---

## 🚀 Setup & Running Locally

### 1. Prerequisites
- Node.js 18+ and npm installed on your machine.
- The FastAPI backend running at `http://localhost:8000`.

### 2. Install Dependencies
Open a terminal in the `frontend/` directory:

```bash
cd frontend
npm install
```

### 3. Configure Environment Variables
Copy the `.env.example` file to `.env`:

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

The default `.env` contents point to your local FastAPI server:
```env
VITE_API_BASE_URL=http://localhost:8000
```

### 4. Start the Vite Dev Server
```bash
npm run dev
```

The frontend will start at: [http://localhost:5173](http://localhost:5173).

---

## 🔄 How Frontend Talks to Backend

| Endpoint | Method | Trigger / Component | Description |
| :--- | :--- | :--- | :--- |
| `/patients` | `GET` | `PatientSelector.jsx` on load | Retrieves list of available patient IDs |
| `/chat` | `POST` | `InputBar.jsx` (text submit) | Submits user text with `session_id` & `patient_id` |
| `/voice-chat` | `POST` | `InputBar.jsx` (mic or upload) | Submits audio file as `multipart/form-data` |
| `/chat/{session_id}`| `DELETE` | `PatientSelector.jsx` (New Chat) | Clears session history on the server |

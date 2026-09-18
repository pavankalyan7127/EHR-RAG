import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.6-flash")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
DATA_DIR = BASE_DIR / "data"
CHUNK_METADATA_PATH = DATA_DIR / "chunk_metadata.json"
FAISS_INDEX_PATH = DATA_DIR / "faiss_index.bin"

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "base")

MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "ehr_rag_db")

raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173")
CORS_ORIGINS = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Authentication & JWT Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ehr-rag-insecure-secret-key-change-in-production-2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import CORS_ORIGINS
from app.core.embeddings import vector_store
from app.core.asr import asr_manager
from app.routes.chat import router as chat_router
from app.routes.voice import router as voice_router
from app.routes.patients import router as patients_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ehr_rag_app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing EHR RAG vector store and models...")
    try:
        vector_store.initialize()
        logger.info("Vector store initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize vector store: {e}", exc_info=True)
        raise e

    try:
        asr_manager.initialize()
        logger.info("Whisper ASR initialized successfully.")
    except Exception as e:
        logger.warning(f"Whisper initialization deferred/encountered issue: {e}")

    yield
    logger.info("Shutting down EHR RAG backend service.")

app = FastAPI(
    title="Multimodal EHR RAG Assistant API",
    description="Backend API for Personalized Medical Question Answering over Electronic Health Records",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(patients_router)

@app.get("/", tags=["Health"])
async def root_health():
    return {
        "status": "healthy",
        "service": "Multimodal EHR RAG Assistant API",
        "loaded_patients": len(vector_store.patient_records),
        "total_chunks": len(vector_store.chunks)
    }

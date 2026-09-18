import json
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from app.config import (
    EMBEDDING_MODEL_NAME,
    CHUNK_METADATA_PATH,
    FAISS_INDEX_PATH
)

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """
    Manages SentenceTransformer embedding model, FAISS vector index,
    and MedQuAD external knowledge chunks.
    Note: Patient EHR records are queried deterministically from MongoDB.
    """
    def __init__(self):
        self.embedding_model: Optional[SentenceTransformer] = None
        self.faiss_index: Optional[faiss.IndexFlatL2] = None
        self.chunks: List[Dict[str, Any]] = []

    def initialize(self):
        """Loads embedding model, chunk metadata, and FAISS index into memory."""
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        logger.info(f"Loading chunk metadata from: {CHUNK_METADATA_PATH}")
        if not CHUNK_METADATA_PATH.exists():
            raise FileNotFoundError(f"Chunk metadata file not found at {CHUNK_METADATA_PATH}")

        with open(CHUNK_METADATA_PATH, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

        logger.info(f"Loaded {len(self.chunks)} total chunks.")

        logger.info(f"Loading FAISS index from: {FAISS_INDEX_PATH}")
        if not FAISS_INDEX_PATH.exists():
            raise FileNotFoundError(f"FAISS index file not found at {FAISS_INDEX_PATH}")

        self.faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
        logger.info(f"FAISS index loaded. Total vectors in index: {self.faiss_index.ntotal}")

    def embed_query(self, query: str) -> np.ndarray:
        """Generates embedding for query text."""
        if not self.embedding_model:
            raise RuntimeError("Embedding model not initialized.")
        emb = self.embedding_model.encode([query], convert_to_numpy=True)
        return emb.astype("float32")

vector_store = VectorStoreManager()

import logging
from typing import List, Dict, Any, Tuple
import os
import numpy as np
from app.core.embeddings import vector_store
from app.db.repositories import get_ehr_records_by_patient

logger = logging.getLogger(__name__)

# Configurable default for maximum relevant patient EHR chunks to include
DEFAULT_TOP_K_EHR = int(os.getenv("DEFAULT_TOP_K_EHR", "5"))

def filter_relevant_ehr_records(
    patient_records: List[Dict[str, Any]],
    query: str,
    top_k: int = DEFAULT_TOP_K_EHR
) -> List[Dict[str, Any]]:
    """
    Locally filters and ranks pre-retrieved patient EHR records based on semantic similarity
    to the user query using the singleton SentenceTransformer embedding model.

    PRIVACY & ISOLATION:
    - Strictly operates ONLY on the records of the already-verified patient_id.
    - Never evaluates or retrieves records from other patients.

    FALLBACK BEHAVIOR:
    - If filtering encounters any error or missing embeddings, gracefully returns the full
      list of patient_records so patient clinical context is never silently discarded.
    """
    total_records = len(patient_records)
    if total_records == 0:
        return []

    # If patient has fewer or equal chunks than the limit, keep all available chunks
    if total_records <= top_k:
        logger.info(
            f"Patient EHR chunks ({total_records}) <= limit ({top_k}). "
            f"Retaining all {total_records} chunks without filtering."
        )
        return patient_records

    try:
        if vector_store.embedding_model is None:
            vector_store.initialize()

        # Extract text content for each chunk (safely avoiding sensitive content in logs)
        chunk_texts = [
            (rec.get("content") or rec.get("text") or "").strip()
            for rec in patient_records
        ]

        # 1. Embed query locally using existing SentenceTransformer singleton
        query_vector = vector_store.embed_query(query)  # Shape: (1, dim)

        # 2. Embed all patient EHR chunks locally
        chunk_vectors = vector_store.embedding_model.encode(
            chunk_texts,
            convert_to_numpy=True
        ).astype("float32")  # Shape: (N, dim)

        # 3. Calculate cosine similarities locally
        q_norm = np.linalg.norm(query_vector, axis=1, keepdims=True) + 1e-9
        query_normed = query_vector / q_norm

        c_norm = np.linalg.norm(chunk_vectors, axis=1, keepdims=True) + 1e-9
        chunks_normed = chunk_vectors / c_norm

        similarities = np.dot(chunks_normed, query_normed.T).flatten()

        # 4. Rank and select top_k most relevant chunks
        ranked_indices = np.argsort(-similarities)[:top_k]
        selected_records = [patient_records[i] for i in ranked_indices]

        # Safe logging: chunk IDs and similarity scores only, NO clinical text
        score_details = [
            f"{patient_records[i].get('chunk_id') or patient_records[i].get('_id', 'unknown')}: {similarities[i]:.4f}"
            for i in ranked_indices
        ]
        logger.info(
            f"Local EHR semantic relevance filtering complete: "
            f"retrieved={total_records}, selected={len(selected_records)}, "
            f"scores=[{', '.join(score_details)}]"
        )

        return selected_records

    except Exception as e:
        # Fallback: preserve clinical context rather than dropping data
        logger.warning(
            f"Local EHR semantic filtering failed: {str(e)}. "
            f"Falling back safely to all {total_records} patient EHR records.",
            exc_info=True
        )
        return patient_records

def search_external_knowledge(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Performs FAISS L2 similarity search to retrieve the most relevant external knowledge chunks.
    Filters to only return external medical knowledge chunks (source_type == 'external').
    """
    if vector_store.faiss_index is None or vector_store.embedding_model is None:
        raise RuntimeError("Vector store is not initialized.")

    query_vector = vector_store.embed_query(query)

    # We retrieve up to 3 * top_k vectors from FAISS to ensure we collect top_k external chunks
    # (since the full FAISS index contains both EHR and external chunks in the original Colab order).
    fetch_k = min(max(top_k * 3, 10), len(vector_store.chunks))
    distances, indices = vector_store.faiss_index.search(query_vector, fetch_k)

    retrieved_external_chunks = []
    for idx, dist in zip(indices[0], distances[0]):
        if idx < 0 or idx >= len(vector_store.chunks):
            continue
        chunk = vector_store.chunks[idx]
        if chunk.get("source_type") == "external":
            retrieved_external_chunks.append(chunk)
            if len(retrieved_external_chunks) >= top_k:
                break

    return retrieved_external_chunks

def retrieve_context(
    patient_id: str,
    query: str,
    top_k_external: int = 3,
    top_k_ehr: int = DEFAULT_TOP_K_EHR
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Executes dual-track retrieval:
    1. Track 1 (Patient EHR): Deterministic retrieval of all EHR chunks for patient_id from MongoDB
       (strict patient isolation), followed by local semantic relevance filtering to select top_k_ehr chunks.
       Falls back safely to all patient records on any filtering error.
    2. Track 2 (External MedQuAD): Semantic FAISS search for top-k external medical reference chunks.
    """
    all_patient_records = get_ehr_records_by_patient(patient_id)
    selected_patient_records = filter_relevant_ehr_records(
        patient_records=all_patient_records,
        query=query,
        top_k=top_k_ehr
    )
    external_chunks = search_external_knowledge(query, top_k=top_k_external)
    return selected_patient_records, external_chunks

def build_context_block(patient_id: str, patient_records: List[Dict[str, Any]], external_chunks: List[Dict[str, Any]]) -> str:
    """
    Builds a clearly formatted context block separating Patient Record from External Medical Knowledge.
    """
    context_parts = []

    # Section 1: Patient Personal EHR
    if patient_records:
        ehr_blocks = []
        for rec in patient_records:
            chunk_id = rec.get("chunk_id") or rec.get("_id", "ehr_unknown")
            content = (rec.get("content") or rec.get("text") or "").strip()
            ehr_blocks.append(f"[Chunk ID: {chunk_id}]\n{content}")
        
        context_parts.append(
            f"=== PATIENT EHR RECORD (Patient ID: {patient_id}) ===\n" + "\n\n".join(ehr_blocks)
        )
    else:
        context_parts.append(f"=== PATIENT EHR RECORD (Patient ID: {patient_id}) ===\n[No record found for this patient ID]")

    # Section 2: External Medical Knowledge Base
    context_parts.append("=== EXTERNAL MEDICAL KNOWLEDGE BASE ===")
    if external_chunks:
        for idx, chunk in enumerate(external_chunks, 1):
            context_parts.append(
                f"[Source {idx} - Chunk ID: {chunk.get('chunk_id')}]\n"
                f"{(chunk.get('text') or chunk.get('content') or '').strip()}"
            )
    else:
        context_parts.append("[No external knowledge retrieved]")

    return "\n\n".join(context_parts)

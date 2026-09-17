import logging
from typing import List, Dict, Any, Tuple, Optional
from app.core.embeddings import vector_store

logger = logging.getLogger(__name__)

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

def retrieve_context(patient_id: str, query: str, top_k_external: int = 3) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Executes hybrid retrieval:
    1. Guaranteed Direct Lookup: Fetches patient EHR note by patient_id.
       (Avoids semantic mismatch where a patient asks a question that does not semantically match their record).
    2. Semantic FAISS Search: Fetches top-k external medical knowledge chunks relevant to the user query.
    """
    patient_chunk = vector_store.get_patient_chunk(patient_id)
    external_chunks = search_external_knowledge(query, top_k=top_k_external)
    return patient_chunk, external_chunks

def build_context_block(patient_chunk: Optional[Dict[str, Any]], external_chunks: List[Dict[str, Any]]) -> str:
    """
    Builds a clearly formatted context block separating Patient Record from External Medical Knowledge.
    """
    context_parts = []

    # Section 1: Patient Personal EHR
    if patient_chunk:
        context_parts.append(
            f"=== PATIENT EHR RECORD (Patient ID: {patient_chunk.get('patient_id')}) ===\n"
            f"[Chunk ID: {patient_chunk.get('chunk_id')}]\n"
            f"{patient_chunk.get('text', '').strip()}"
        )
    else:
        context_parts.append("=== PATIENT EHR RECORD ===\n[No record found for this patient ID]")

    # Section 2: External Medical Knowledge Base
    context_parts.append("\n=== EXTERNAL MEDICAL KNOWLEDGE BASE ===")
    if external_chunks:
        for idx, chunk in enumerate(external_chunks, 1):
            context_parts.append(
                f"[Source {idx} - Chunk ID: {chunk.get('chunk_id')}]\n"
                f"{chunk.get('text', '').strip()}"
            )
    else:
        context_parts.append("[No external knowledge retrieved]")

    return "\n\n".join(context_parts)

import logging
from typing import List, Dict, Any, Tuple
from app.core.embeddings import vector_store
from app.db.repositories import get_ehr_records_by_patient

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

def retrieve_context(patient_id: str, query: str, top_k_external: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Executes dual-track retrieval:
    1. Track 1 (Patient EHR): Guaranteed deterministic retrieval of all EHR chunks for patient_id from MongoDB.
       (Preserves privacy and guarantees complete patient clinical context without vector similarity drift).
    2. Track 2 (External MedQuAD): Semantic FAISS search for top-k external medical reference chunks.
    """
    patient_records = get_ehr_records_by_patient(patient_id)
    external_chunks = search_external_knowledge(query, top_k=top_k_external)
    return patient_records, external_chunks

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

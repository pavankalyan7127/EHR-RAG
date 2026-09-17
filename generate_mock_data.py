import json
from pathlib import Path
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

DATA_DIR = Path(__file__).resolve().parent / "backend" / "app" / "data"
CHUNK_FILE = DATA_DIR / "chunk_metadata.json"
INDEX_FILE = DATA_DIR / "faiss_index.bin"

def main():
    if not CHUNK_FILE.exists():
        print(f"Error: {CHUNK_FILE} not found!")
        return

    with open(CHUNK_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Loaded {len(chunks)} chunks from {CHUNK_FILE}")
    print("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    texts = [c["text"] for c in chunks]
    print(f"Computing embeddings for {len(texts)} chunks...")
    embeddings = model.encode(texts, convert_to_numpy=True).astype("float32")

    dim = embeddings.shape[1]
    print(f"Creating FAISS IndexFlatL2 with dimension {dim}...")
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    faiss.write_index(index, str(INDEX_FILE))
    print(f"Successfully wrote FAISS index ({index.ntotal} vectors) to {INDEX_FILE}")

if __name__ == "__main__":
    main()

import os
import sys
import re
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import CHUNK_METADATA_PATH
from app.db.connection import db_manager
from app.db.repositories import upsert_patient, upsert_ehr_record

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("seed_database")

def extract_demographics(text: str) -> tuple[int | None, str | None]:
    """Extracts approximate age and gender from synthetic EHR text if present."""
    age = None
    gender = None
    
    # Matches patterns like '58-year-old male', '65-year-old female'
    match = re.search(r"(\d+)[-\s]year[-\s]old\s+(male|female|man|woman)", text, re.IGNORECASE)
    if match:
        age = int(match.group(1))
        gender_raw = match.group(2).lower()
        gender = "Male" if gender_raw in ["male", "man"] else "Female"
    return age, gender

def seed_database():
    """
    Seeds the MongoDB database with synthetic patients and EHR records
    from chunk_metadata.json idempotently.
    """
    logger.info("Connecting to MongoDB for database seeding...")
    try:
        db_manager.connect()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    if not CHUNK_METADATA_PATH.exists():
        logger.error(f"Chunk metadata file not found at: {CHUNK_METADATA_PATH}")
        sys.exit(1)

    logger.info(f"Reading chunk metadata from {CHUNK_METADATA_PATH}...")
    with open(CHUNK_METADATA_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    ehr_chunks = [c for c in chunks if c.get("source_type") == "ehr" and c.get("patient_id")]
    logger.info(f"Found {len(ehr_chunks)} EHR chunks across metadata.")

    # Group EHR records by patient_id
    patients_map = {}
    for chunk in ehr_chunks:
        pid = chunk["patient_id"]
        if pid not in patients_map:
            patients_map[pid] = []
        patients_map[pid].append(chunk)

    seeded_patients_count = 0
    seeded_records_count = 0

    now = datetime.now(timezone.utc)

    for patient_id, p_chunks in patients_map.items():
        # Derive demographic info from first available EHR chunk text
        first_text = p_chunks[0].get("text", "")
        age, gender = extract_demographics(first_text)

        patient_doc = {
            "_id": patient_id,
            "name": f"Patient {patient_id}",
            "age": age,
            "gender": gender,
            "created_at": now
        }
        upsert_patient(patient_doc)
        seeded_patients_count += 1

        # Seed each EHR record for this patient
        for chunk in p_chunks:
            record_doc = {
                "_id": chunk.get("chunk_id", f"ehr_{patient_id}"),
                "patient_id": patient_id,
                "chunk_id": chunk.get("chunk_id", f"ehr_{patient_id}"),
                "chunk_type": "clinical_note",
                "content": chunk.get("text", "").strip(),
                "metadata": {
                    "source": "EHR",
                    "source_type": chunk.get("source_type", "ehr"),
                },
                "created_at": now
            }
            upsert_ehr_record(record_doc)
            seeded_records_count += 1

    logger.info(f"Seeding completed successfully: {seeded_patients_count} patients, {seeded_records_count} EHR records upserted.")
    db_manager.disconnect()

if __name__ == "__main__":
    seed_database()

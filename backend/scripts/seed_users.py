import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.connection import db_manager
from app.db.repositories import get_all_patient_ids, upsert_user, get_user
from app.core.auth import hash_password

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("seed_users")


def seed_users():
    """
    Seeds user accounts for all existing demo patients in MongoDB.
    Demo credentials:
      patient_id: P001 -> password: P001
      patient_id: P017 -> password: P017
    
    Security:
    - Passwords are strictly hashed with Argon2id.
    - Plaintext passwords are NEVER stored in the database.
    - Plaintext passwords are NEVER printed in logs.
    - Idempotent: safe to run multiple times without duplicating or corrupting.
    """
    logger.info("Connecting to MongoDB for user provisioning...")
    try:
        db_manager.connect()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    patient_ids = get_all_patient_ids()
    if not patient_ids:
        logger.warning("No patients found in the database. Run seed_database.py first.")
        db_manager.disconnect()
        return

    logger.info(f"Found {len(patient_ids)} patients in database to provision accounts for.")
    now = datetime.now(timezone.utc)
    seeded_count = 0
    updated_count = 0

    for pid in patient_ids:
        existing_user = get_user(pid)
        # Compute Argon2 hash of initial password (password == patient_id)
        pwd_hash = hash_password(pid)

        user_doc = {
            "_id": pid,
            "patient_id": pid,
            "password_hash": pwd_hash,
            "role": "patient",
            "is_active": True,
            "created_at": existing_user.get("created_at", now) if existing_user else now,
            "updated_at": now
        }
        upsert_user(user_doc)

        if existing_user:
            updated_count += 1
        else:
            seeded_count += 1

    # Ensure default administrator account is provisioned
    existing_admin = get_user("admin")
    if not existing_admin:
        admin_doc = {
            "_id": "admin",
            "patient_id": "admin",
            "password_hash": hash_password("Admin@123"),
            "role": "admin",
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        upsert_user(admin_doc)
        logger.info("Admin user 'admin' provisioned (role: admin).")

    logger.info(
        f"User provisioning completed successfully: {seeded_count} newly created, "
        f"{updated_count} updated. Total users: {len(patient_ids)}."
    )
    db_manager.disconnect()


if __name__ == "__main__":
    seed_users()

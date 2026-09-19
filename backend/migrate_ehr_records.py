import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.db.connection import db_manager
from app.db.collections import (
    get_ehr_records_collection,
    get_patients_collection,
    get_users_collection
)
from app.core.auth import hash_password

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("migration")


def provision_admin_user(admin_id: str = "admin", plain_password: str = "Admin@123"):
    """
    Ensures an initial administrator account exists in the users collection.
    Idempotent: will not overwrite if admin already exists.
    """
    users_col = get_users_collection()
    existing_admin = users_col.find_one({"patient_id": admin_id})
    if existing_admin:
        logger.info(f"Admin account '{admin_id}' already present. Role: {existing_admin.get('role')}.")
        return

    now = datetime.now(timezone.utc)
    pwd_hash = hash_password(plain_password)
    admin_doc = {
        "_id": admin_id,
        "patient_id": admin_id,
        "password_hash": pwd_hash,
        "role": "admin",
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }
    users_col.replace_one({"patient_id": admin_id}, admin_doc, upsert=True)
    logger.info(f"Administrator account '{admin_id}' provisioned successfully (Role: admin).")


def run_migration():
    """
    Safely and idempotently migrates legacy EHR record IDs (ehr_P001 -> ehr_P001_001)
    with strict step-by-step verification before deleting any legacy documents.
    """
    print("\n" + "=" * 60)
    print("MIGRATION: LEGACY EHR RECORDS -> MULTI-RECORD STRUCTURE")
    print("=" * 60)

    try:
        db_manager.connect()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    ehr_col = get_ehr_records_collection()
    patients_col = get_patients_collection()

    # Step 1: Provision default admin account
    provision_admin_user()

    # Step 2: Identify legacy records: ehr_P### without suffix _###
    all_records = list(ehr_col.find({}))
    legacy_records = [
        r for r in all_records
        if r["_id"].startswith("ehr_P") and len(r["_id"].split("_")) == 2
    ]

    print(f"\nFound {len(legacy_records)} legacy record(s) pending verification/migration.")
    print("Starting step-by-step verified migration...\n")

    successful_migrations = 0
    failed_migrations = 0

    for legacy in legacy_records:
        old_id = legacy["_id"]
        patient_id = legacy["patient_id"]
        new_id = f"{old_id}_001"

        try:
            # 1. Read legacy record
            content = legacy.get("content", "")
            metadata = legacy.get("metadata", {"source": "EHR", "source_type": "ehr"})
            created_at = legacy.get("created_at") or datetime.now(timezone.utc)
            recorded_at = legacy.get("recorded_at") or created_at
            updated_at = legacy.get("updated_at") or created_at
            chunk_type = legacy.get("chunk_type", "clinical_note")

            # 2. Create/upsert new record with _001 ID
            new_doc = {
                "_id": new_id,
                "patient_id": patient_id,
                "chunk_id": new_id,
                "chunk_type": chunk_type,
                "content": content,
                "metadata": metadata,
                "recorded_at": recorded_at,
                "created_at": created_at,
                "updated_at": updated_at
            }
            ehr_col.replace_one({"_id": new_id}, new_doc, upsert=True)

            # 3. Step-by-step Verification
            verified_doc = ehr_col.find_one({"_id": new_id})
            assert verified_doc is not None, f"Verification failed: new record {new_id} not found."
            assert verified_doc["patient_id"] == patient_id, f"Patient ID mismatch on {new_id}."
            assert verified_doc["content"] == content, f"Content mismatch on {new_id}."
            assert verified_doc["metadata"] == metadata, f"Metadata mismatch on {new_id}."
            assert verified_doc.get("recorded_at") is not None, f"recorded_at missing on {new_id}."
            assert verified_doc.get("created_at") is not None, f"created_at missing on {new_id}."
            assert verified_doc.get("updated_at") is not None, f"updated_at missing on {new_id}."

            # 4. Update patient last_ehr_seq to at least 1
            patients_col.update_one(
                {"_id": patient_id},
                {"$max": {"last_ehr_seq": 1}}
            )

            # 5. ONLY now safely remove legacy record
            del_res = ehr_col.delete_one({"_id": old_id})
            assert del_res.deleted_count == 1, f"Failed to delete legacy record {old_id}."

            print(f"  {old_id} -> {new_id} [OK]")
            successful_migrations += 1

        except Exception as err:
            logger.error(f"Migration error for {old_id}: {err}", exc_info=True)
            print(f"  {old_id} [FAILED] ({err})")
            failed_migrations += 1

    # Step 3: Ensure all patients have last_ehr_seq initialized
    all_patients = list(patients_col.find({}))
    for p in all_patients:
        pid = p["_id"]
        # Count max suffix present
        recs = ehr_col.find({"patient_id": pid})
        max_seq = 0
        for r in recs:
            rid = r.get("_id", "")
            if f"ehr_{pid}_" in rid:
                try:
                    seq_num = int(rid.split("_")[-1])
                    max_seq = max(max_seq, seq_num)
                except ValueError:
                    pass
        patients_col.update_one(
            {"_id": pid},
            {"$max": {"last_ehr_seq": max_seq}}
        )

    # Final counts and validation
    remaining_legacy = ehr_col.count_documents({
        "_id": {"$regex": r"^ehr_P\d+$"}
    })
    total_migrated = ehr_col.count_documents({
        "_id": {"$regex": r"^ehr_P\d+_\d+$"}
    })

    print("\n" + "-" * 60)
    print("MIGRATION SUMMARY")
    print("-" * 60)
    print(f"Successfully migrated: {successful_migrations}")
    print(f"Failed: {failed_migrations}")
    print(f"Legacy records remaining: {remaining_legacy}")
    print(f"Total active multi-record EHR documents: {total_migrated}")
    print("-" * 60 + "\n")

    if failed_migrations == 0 and remaining_legacy == 0:
        print("[SUCCESS] All EHR records successfully and safely migrated to multi-record format!\n")
    else:
        print("[WARNING] Some records could not be fully migrated or legacy records remain.\n")

    db_manager.disconnect()


if __name__ == "__main__":
    run_migration()

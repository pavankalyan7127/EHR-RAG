import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status

from app.models.schemas import (
    AdminPatientItem,
    AdminPatientCreate,
    AdminPatientUpdate,
    AdminRecordCreate,
    AdminRecordUpdate,
    AdminRecordResponse
)
from app.core.auth import require_admin, hash_password, AuthenticatedPatient
from app.db.repositories import (
    get_patient,
    get_all_patients_with_metadata,
    generate_next_patient_id,
    upsert_patient,
    update_patient_demographics,
    set_patient_active_status,
    delete_patient_cascade,
    get_user,
    upsert_user,
    get_ehr_records_by_patient,
    get_ehr_record_by_id,
    create_ehr_record,
    update_ehr_record,
    delete_ehr_record
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


# ==============================================================================
# Patient Management Endpoints
# ==============================================================================

@router.get("/patients", response_model=List[AdminPatientItem])
async def list_patients(
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Retrieves all registered patients with demographic summary, account active status,
    and total count of medical records.
    """
    try:
        return get_all_patients_with_metadata()
    except Exception as e:
        logger.error(f"Error fetching admin patient list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve patient registry."
        )


@router.post("/patients", response_model=AdminPatientItem, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: AdminPatientCreate,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Creates a new patient profile and associated user credentials account.
    - Generates next sequential patient ID (e.g. 'P031') if none provided.
    - Enforces patient_id uniqueness across patients and users.
    - Hashes initial password with Argon2id.
    - Sets role = 'patient' and is_active = True.
    - Does NOT create an EHR record automatically (patients can exist with 0 records).
    """
    pid = payload.patient_id.strip() if payload.patient_id else generate_next_patient_id()

    # Uniqueness check
    if get_patient(pid) or get_user(pid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient with ID '{pid}' already exists in the system."
        )

    now = datetime.now(timezone.utc)
    patient_doc = {
        "_id": pid,
        "name": payload.name.strip(),
        "age": payload.age,
        "gender": payload.gender,
        "last_ehr_seq": 0,
        "created_at": now
    }
    upsert_patient(patient_doc)

    raw_password = payload.password if (payload.password and payload.password.strip()) else pid
    password_hash = hash_password(raw_password)

    user_doc = {
        "_id": pid,
        "patient_id": pid,
        "password_hash": password_hash,
        "role": "patient",
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }
    upsert_user(user_doc)

    logger.info(f"Admin '{current_admin.patient_id}' created new patient '{pid}' ({payload.name}).")
    return AdminPatientItem(
        patient_id=pid,
        name=patient_doc["name"],
        age=patient_doc["age"],
        gender=patient_doc["gender"],
        is_active=True,
        record_count=0,
        created_at=now
    )


@router.get("/patients/{patient_id}", response_model=AdminPatientItem)
async def get_patient_detail(
    patient_id: str,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """Retrieves specific patient profile with active status and record count."""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found."
        )

    user = get_user(patient_id) or {}
    records = get_ehr_records_by_patient(patient_id)

    return AdminPatientItem(
        patient_id=patient["_id"],
        name=patient.get("name", f"Patient {patient_id}"),
        age=patient.get("age"),
        gender=patient.get("gender"),
        is_active=user.get("is_active", True),
        record_count=len(records),
        created_at=patient.get("created_at")
    )


@router.put("/patients/{patient_id}", response_model=AdminPatientItem)
async def update_patient(
    patient_id: str,
    payload: AdminPatientUpdate,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Updates patient demographics and/or account active status.
    Preserves all existing medical records, sessions, and chat data.
    """
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found."
        )

    # 1. Update demographics if provided
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name.strip()
    if payload.age is not None:
        update_data["age"] = payload.age
    if payload.gender is not None:
        update_data["gender"] = payload.gender

    if update_data:
        update_patient_demographics(patient_id, update_data)

    # 2. Update active status if provided
    if payload.is_active is not None:
        set_patient_active_status(patient_id, payload.is_active)

    # Reload updated records
    updated_p = get_patient(patient_id)
    updated_u = get_user(patient_id) or {}
    records = get_ehr_records_by_patient(patient_id)

    logger.info(f"Admin '{current_admin.patient_id}' updated patient profile for '{patient_id}'.")
    return AdminPatientItem(
        patient_id=patient_id,
        name=updated_p.get("name"),
        age=updated_p.get("age"),
        gender=updated_p.get("gender"),
        is_active=updated_u.get("is_active", True),
        record_count=len(records),
        created_at=updated_p.get("created_at")
    )


@router.delete("/patients/{patient_id}")
async def delete_patient_endpoint(
    patient_id: str,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Explicit permanent deletion of a patient and all cascading dependencies.
    Admin dashboard primarily exposes deactivation (is_active=false); this endpoint
    is reserved for explicit, confirmed hard removals.
    """
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found."
        )

    success = delete_patient_cascade(patient_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete patient '{patient_id}'."
        )

    logger.warning(f"Admin '{current_admin.patient_id}' permanently deleted patient '{patient_id}' and all associated records.")
    return {
        "success": True,
        "patient_id": patient_id,
        "message": f"Patient '{patient_id}' and all associated records permanently removed."
    }


# ==============================================================================
# Multi-Record EHR CRUD Endpoints
# ==============================================================================

@router.get("/patients/{patient_id}/records", response_model=List[AdminRecordResponse])
async def list_patient_ehr_records(
    patient_id: str,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Retrieves all EHR records for the specified patient, ordered newest first (by recorded_at).
    """
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found."
        )

    records = get_ehr_records_by_patient(patient_id, sort_newest_first=True)
    results = []
    for r in records:
        results.append(AdminRecordResponse(
            _id=r["_id"],
            patient_id=r["patient_id"],
            chunk_id=r.get("chunk_id", r["_id"]),
            chunk_type=r.get("chunk_type", "clinical_note"),
            content=r.get("content", ""),
            metadata=r.get("metadata", {}),
            recorded_at=r.get("recorded_at", r.get("created_at")),
            created_at=r.get("created_at"),
            updated_at=r.get("updated_at", r.get("created_at"))
        ))
    return results


@router.post("/patients/{patient_id}/records", response_model=AdminRecordResponse, status_code=status.HTTP_201_CREATED)
async def add_patient_ehr_record(
    patient_id: str,
    payload: AdminRecordCreate,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Adds a new medical record for the specified patient.
    - Automatically generates the next monotonic sequence ID (e.g. 'ehr_P001_002').
    - Sequence numbers are strictly monotonic and never reused.
    - Separately records recorded_at, created_at, and updated_at.
    - Newly added record becomes immediately available to the RAG pipeline.
    """
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found."
        )

    doc = create_ehr_record(
        patient_id=patient_id,
        content=payload.content,
        chunk_type=payload.chunk_type,
        recorded_at=payload.recorded_at
    )

    logger.info(f"Admin '{current_admin.patient_id}' added EHR record '{doc['_id']}' for patient '{patient_id}'.")
    return AdminRecordResponse(
        _id=doc["_id"],
        patient_id=doc["patient_id"],
        chunk_id=doc["chunk_id"],
        chunk_type=doc["chunk_type"],
        content=doc["content"],
        metadata=doc["metadata"],
        recorded_at=doc["recorded_at"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"]
    )


@router.put("/patients/{patient_id}/records/{record_id}", response_model=AdminRecordResponse)
async def update_patient_ehr_record(
    patient_id: str,
    record_id: str,
    payload: AdminRecordUpdate,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Updates an existing EHR record for a patient.
    Updates content, chunk_type, and/or recorded_at, and refreshes updated_at.
    """
    record = get_ehr_record_by_id(record_id, patient_id=patient_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EHR record '{record_id}' for patient '{patient_id}' not found."
        )

    updated_doc = update_ehr_record(
        record_id=record_id,
        patient_id=patient_id,
        content=payload.content,
        chunk_type=payload.chunk_type,
        recorded_at=payload.recorded_at
    )

    if not updated_doc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update EHR record '{record_id}'."
        )

    logger.info(f"Admin '{current_admin.patient_id}' updated EHR record '{record_id}' for patient '{patient_id}'.")
    return AdminRecordResponse(
        _id=updated_doc["_id"],
        patient_id=updated_doc["patient_id"],
        chunk_id=updated_doc["chunk_id"],
        chunk_type=updated_doc["chunk_type"],
        content=updated_doc["content"],
        metadata=updated_doc["metadata"],
        recorded_at=updated_doc.get("recorded_at", updated_doc.get("created_at")),
        created_at=updated_doc["created_at"],
        updated_at=updated_doc["updated_at"]
    )


@router.delete("/patients/{patient_id}/records/{record_id}")
async def delete_patient_ehr_record(
    patient_id: str,
    record_id: str,
    current_admin: AuthenticatedPatient = Depends(require_admin)
):
    """
    Deletes a single EHR record from ehr_records.
    Guarantees sequence IDs are never reused upon deletion.
    """
    record = get_ehr_record_by_id(record_id, patient_id=patient_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EHR record '{record_id}' for patient '{patient_id}' not found."
        )

    success = delete_ehr_record(record_id, patient_id=patient_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete EHR record '{record_id}'."
        )

    logger.info(f"Admin '{current_admin.patient_id}' deleted EHR record '{record_id}' for patient '{patient_id}'.")
    return {
        "success": True,
        "record_id": record_id,
        "patient_id": patient_id,
        "message": f"EHR record '{record_id}' removed successfully."
    }

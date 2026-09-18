import logging
from fastapi import APIRouter, HTTPException, Depends, status
from app.models.schemas import PatientsResponse, PatientProfileResponse
from app.db.repositories import get_all_patient_ids, get_patient
from app.core.auth import get_current_patient, AuthenticatedPatient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Patients"])


@router.get("/patients/me", response_model=PatientProfileResponse)
async def get_current_patient_profile(
    current_patient: AuthenticatedPatient = Depends(get_current_patient)
):
    """
    Retrieves the clinical demographic profile for the currently authenticated patient.
    Guarantees that a patient can only view their own profile.
    """
    patient_doc = get_patient(current_patient.patient_id)
    if not patient_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient record for '{current_patient.patient_id}' not found."
        )

    return PatientProfileResponse(
        patient_id=current_patient.patient_id,
        name=patient_doc.get("name", f"Patient {current_patient.patient_id}"),
        age=patient_doc.get("age"),
        gender=patient_doc.get("gender")
    )


@router.get("/patients", response_model=PatientsResponse)
async def get_patients_endpoint():
    """
    Retrieves the list of registered patient IDs from MongoDB.
    Kept for diagnostic and database verification purposes.
    """
    try:
        patient_ids = get_all_patient_ids()
        return PatientsResponse(patients=patient_ids)
    except Exception as e:
        logger.error(f"Failed to fetch patient IDs from MongoDB: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve patient records from database."
        )

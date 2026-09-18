import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import PatientsResponse
from app.db.repositories import get_all_patient_ids

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Patients"])

@router.get("/patients", response_model=PatientsResponse)
async def get_patients_endpoint():
    """
    Retrieves the list of all registered patient IDs from MongoDB.
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

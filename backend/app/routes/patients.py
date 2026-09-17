from fastapi import APIRouter
from app.models.schemas import PatientsResponse
from app.core.embeddings import vector_store

router = APIRouter(prefix="", tags=["Patients"])

@router.get("/patients", response_model=PatientsResponse)
async def get_patients_endpoint():
    patient_ids = vector_store.get_all_patient_ids()
    return PatientsResponse(patients=patient_ids)

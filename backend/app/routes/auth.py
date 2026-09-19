import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import LoginRequest, TokenResponse
from app.db.repositories import get_user
from app.core.auth import verify_password, create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login_endpoint(request: LoginRequest):
    """
    Authenticates a patient using patient_id and password.
    
    Security:
    - Never reveals whether the patient ID exists or password was incorrect.
    - Password verified using Argon2id.
    - Issues a signed JWT identifying the patient.
    """
    patient_id = request.patient_id.strip()
    password = request.password

    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid patient ID or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not patient_id or not password:
        raise generic_error

    user = get_user(patient_id)
    if not user:
        logger.info(f"Failed login attempt: patient '{patient_id}' not found.")
        raise generic_error

    if not user.get("is_active", True):
        logger.warning(f"Deactivated account login attempt: patient '{patient_id}'.")
        raise generic_error

    password_hash = user.get("password_hash")
    if not password_hash or not verify_password(password, password_hash):
        logger.info(f"Failed login attempt: invalid password for patient '{patient_id}'.")
        raise generic_error

    role = user.get("role", "patient")
    access_token = create_access_token(patient_id=patient_id, role=role)
    logger.info(f"Successful login for user '{patient_id}' with role '{role}'. JWT token issued.")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        patient_id=patient_id,
        role=role
    )

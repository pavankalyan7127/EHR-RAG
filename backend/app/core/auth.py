import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.db.repositories import get_user

logger = logging.getLogger(__name__)

# Reusable Argon2 PasswordHasher instance
_pwd_hasher = PasswordHasher()

# HTTP Bearer security scheme for OpenAPI and dependency injection
security = HTTPBearer(auto_error=False)


class AuthenticatedPatient(BaseModel):
    """Represents the validated authenticated patient identity."""
    patient_id: str
    role: str = "patient"
    is_active: bool = True


def hash_password(plain_password: str) -> str:
    """
    Hashes a plaintext password using Argon2id.
    Never stores plaintext passwords.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    return _pwd_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against an Argon2 hash.
    Safely returns False on mismatch or corrupted hash.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _pwd_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during password verification: {e}")
        return False


def create_access_token(patient_id: str, role: str = "patient", expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a signed JWT access token identifying the user via the 'sub' claim
    and embedding their authorized role ('patient' or 'admin').
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": patient_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decodes and validates a JWT access token.
    Raises jwt.PyJWTError subclasses on failure.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def _validate_token_and_get_patient(token: Optional[str]) -> AuthenticatedPatient:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
        patient_id: Optional[str] = payload.get("sub")
        if not patient_id:
            raise credentials_exception
    except jwt.PyJWTError as e:
        logger.warning(f"JWT validation failure: {e}")
        raise credentials_exception

    # Confirm user exists and is active in MongoDB
    user_doc = get_user(patient_id)
    if not user_doc:
        logger.warning(f"Authenticated token has patient_id '{patient_id}' which does not exist in users collection.")
        raise credentials_exception

    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient account is deactivated."
        )

    return AuthenticatedPatient(
        patient_id=patient_id,
        role=user_doc.get("role", "patient"),
        is_active=user_doc.get("is_active", True)
    )


async def get_current_patient(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedPatient:
    """
    FastAPI dependency to extract and validate the authenticated patient from the Bearer JWT.
    Raises 401 Unauthorized for missing or invalid tokens.
    """
    token = credentials.credentials if credentials else None
    return _validate_token_and_get_patient(token)


async def get_current_patient_flexible(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = Query(None, description="JWT token via query param (used for audio media streaming)")
) -> AuthenticatedPatient:
    """
    FastAPI dependency that accepts JWT via either Authorization: Bearer header OR ?token=<jwt> query parameter.
    Essential for native HTML5 <audio> elements where custom request headers cannot be attached.
    """
    raw_token = credentials.credentials if (credentials and credentials.credentials) else token
    return _validate_token_and_get_patient(raw_token)


async def require_admin(
    current_user: AuthenticatedPatient = Depends(get_current_patient)
) -> AuthenticatedPatient:
    """
    FastAPI dependency to enforce administrative role (role == 'admin').
    Rejects patient accounts with 403 Forbidden.
    """
    if current_user.role != "admin":
        logger.warning(
            f"Unauthorized administrative access rejected for user '{current_user.patient_id}' (role: '{current_user.role}')."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required."
        )
    return current_user


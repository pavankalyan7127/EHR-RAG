from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# ==============================================================================
# Database Document Schemas
# ==============================================================================

class UserDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Primary key, typically the patient_id")
    patient_id: str = Field(..., description="Unique patient identifier, e.g. 'P001'")
    password_hash: str = Field(..., description="Argon2 password hash")
    role: str = Field(default="patient", description="User role ('patient', 'admin')")
    is_active: bool = Field(default=True, description="Account active status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp in UTC")

    model_config = ConfigDict(populate_by_name=True)


class PatientDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique patient identifier, e.g. 'P001'")
    name: str = Field(..., description="Patient name or display label")
    age: Optional[int] = Field(None, description="Patient age in years")
    gender: Optional[str] = Field(None, description="Patient gender")
    last_ehr_seq: int = Field(default=0, description="Highest monotonic EHR sequence number generated for this patient")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp in UTC")

    model_config = ConfigDict(populate_by_name=True)


class EHRRecordDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique EHR record identifier, e.g. 'ehr_P001_001'")
    patient_id: str = Field(..., description="Associated patient identifier, e.g. 'P001'")
    chunk_id: str = Field(..., description="Chunk ID for provenance citation, e.g. 'ehr_P001_001'")
    chunk_type: str = Field(default="clinical_note", description="Category or chunk type, e.g. 'clinical_note', 'medication'")
    content: str = Field(..., description="Text content of the EHR record note")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the medical event/consultation occurred in UTC")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When record was entered into the system in UTC")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When record was last modified in UTC")

    model_config = ConfigDict(populate_by_name=True)


class SessionDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique session UUID")
    patient_id: str = Field(..., description="Identifier of the patient bound to this session")
    title: Optional[str] = Field(default="New Conversation", description="Descriptive or generated session title")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Session creation timestamp in UTC")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last active timestamp in UTC")
    status: str = Field(default="active", description="Session status ('active', 'archived')")

    model_config = ConfigDict(populate_by_name=True)


class MessageDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique message identifier")
    session_id: str = Field(..., description="Session UUID to which this message belongs")
    patient_id: str = Field(..., description="Patient identifier associated with the session")
    role: Literal["user", "assistant"] = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Message text content")
    input_type: str = Field(default="text", description="Input modality ('text', 'voice')")
    audio_file_id: Optional[str] = Field(None, description="GridFS file ID for original audio")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the message in UTC")
    sources: List[str] = Field(default_factory=list, description="List of source chunk IDs used for grounding provenance")

    model_config = ConfigDict(populate_by_name=True)


# ==============================================================================
# API Request / Response Schemas
# ==============================================================================

# Authentication Schemas
class LoginRequest(BaseModel):
    patient_id: str = Field(..., min_length=1, description="Patient ID / Patient Number, e.g. 'P017'")
    password: str = Field(..., min_length=1, description="Patient password")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT Bearer access token")
    token_type: str = Field(default="bearer", description="Token type")
    patient_id: str = Field(..., description="Authenticated user / patient identifier")
    role: str = Field(default="patient", description="User role ('patient' or 'admin')")


class PatientProfileResponse(BaseModel):
    patient_id: str = Field(..., description="Patient identifier")
    name: str = Field(..., description="Patient full name")
    age: Optional[int] = Field(None, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient gender")


# Chat Schemas
class ChatMessage(BaseModel):
    id: Optional[str] = Field(None, description="Unique message identifier")
    role: Literal["user", "assistant"] = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Content of the message")
    input_type: Optional[str] = Field(default="text", description="Input modality ('text', 'voice')")
    audio_file_id: Optional[str] = Field(None, description="GridFS audio file ID")
    audio_url: Optional[str] = Field(None, description="Audio playback URL")
    timestamp: Optional[datetime] = Field(None, description="Optional message timestamp")
    sources: Optional[List[str]] = Field(default_factory=list, description="Grounding sources")


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Unique session identifier for multi-turn chat")
    message: str = Field(..., min_length=1, description="User question or query text")
    patient_id: Optional[str] = Field(None, description="Optional patient ID (derived automatically from auth token)")
    target_language: Optional[str] = Field(None, description="Optional target language code (e.g. 'en', 'bn', 'gu', 'hi', 'mr', 'pa', 'ta', 'te', 'ur')")


class ChatResponse(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    answer: str = Field(..., description="Generated answer from the multimodal RAG assistant")
    patient_sources: List[str] = Field(default_factory=list, description="List of patient EHR chunk IDs or descriptions used")
    external_sources: List[str] = Field(default_factory=list, description="List of external knowledge chunk IDs used")
    history: List[ChatMessage] = Field(default_factory=list, description="Updated multi-turn conversation history for this session")
    language: Optional[str] = Field(None, description="Language of the returned answer, e.g. 'en', 'ta', 'te', 'hi'")
    audio_base64: Optional[str] = Field(None, description="Base64-encoded neural TTS audio for the returned answer")
    audio_format: Optional[str] = Field(None, description="Audio format of the generated TTS audio, e.g. 'wav'")
    canonical_answer: Optional[str] = Field(None, description="Canonical English medical answer produced by RAG reasoning")


class VoiceChatResponse(ChatResponse):
    transcribed_text: str = Field(..., description="Transcribed user query produced by the multilingual NLP service")
    audio_file_id: Optional[str] = Field(None, description="GridFS audio file ID")
    audio_url: Optional[str] = Field(None, description="Audio playback URL for the original recording")


class LocalizationRequest(BaseModel):
    english_response: str = Field(..., min_length=1, description="Canonical English medical response to localize")
    target_language: str = Field(..., description="Target language code, e.g. 'en', 'bn', 'gu', 'hi', 'mr', 'pa', 'ta', 'te', 'ur'")


class LocalizationResponse(BaseModel):
    target_language: str = Field(..., description="Target language code")
    native_text: str = Field(..., description="Localized response text in the target language")
    audio_base64: Optional[str] = Field(None, description="Base64-encoded neural TTS audio")
    audio_format: Optional[str] = Field(default="wav", description="Audio format of the generated TTS audio, e.g. 'wav'")


# Session Management Schemas
class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default="New Conversation", description="Initial session title")


class SessionSummary(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    patient_id: str = Field(..., description="Associated patient identifier")
    title: str = Field(..., description="Session display title")
    created_at: datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime = Field(..., description="Session last updated timestamp")


class SessionDetailResponse(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    patient_id: str = Field(..., description="Associated patient identifier")
    title: str = Field(..., description="Session title")
    messages: List[ChatMessage] = Field(default_factory=list, description="Chronological message history")


class DeleteSessionResponse(BaseModel):
    session_id: str
    message: str
    cleared: bool


class PatientsResponse(BaseModel):
    patients: List[str] = Field(..., description="List of available patient IDs for selection")


# ==============================================================================
# Admin Dashboard Schemas
# ==============================================================================

class AdminPatientItem(BaseModel):
    patient_id: str = Field(..., description="Unique patient identifier, e.g. 'P001'")
    name: str = Field(..., description="Patient full name")
    age: Optional[int] = Field(None, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient gender")
    is_active: bool = Field(default=True, description="Account active status")
    record_count: int = Field(default=0, description="Total number of EHR records")
    created_at: Optional[datetime] = Field(None, description="Account creation timestamp")


class AdminPatientCreate(BaseModel):
    patient_id: Optional[str] = Field(None, description="Optional custom patient ID (e.g. 'P031'). If omitted, automatically generated.")
    name: str = Field(..., min_length=1, description="Patient full name")
    age: Optional[int] = Field(None, ge=0, le=130, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient gender ('Male', 'Female', etc.)")
    password: Optional[str] = Field(None, description="Initial account password (defaults to patient_id)")


class AdminPatientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, description="Updated patient name")
    age: Optional[int] = Field(None, ge=0, le=130, description="Updated age")
    gender: Optional[str] = Field(None, description="Updated gender")
    is_active: Optional[bool] = Field(None, description="Activate or deactivate account")


class AdminRecordCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Medical note / consultation text")
    chunk_type: str = Field(default="clinical_note", description="Record type ('clinical_note', 'medication', 'lab_result', etc.)")
    recorded_at: Optional[datetime] = Field(None, description="When medical consultation/event occurred in UTC (defaults to current time)")


class AdminRecordUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, description="Updated note text")
    chunk_type: Optional[str] = Field(None, description="Updated record type")
    recorded_at: Optional[datetime] = Field(None, description="Updated consultation timestamp in UTC")


class AdminRecordResponse(BaseModel):
    id: str = Field(..., alias="_id", description="Unique EHR record identifier, e.g. 'ehr_P001_001'")
    patient_id: str = Field(..., description="Associated patient identifier")
    chunk_id: str = Field(..., description="Chunk ID for provenance citation")
    chunk_type: str = Field(default="clinical_note", description="Category or chunk type")
    content: str = Field(..., description="EHR note text")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")
    recorded_at: datetime = Field(..., description="Timestamp when event occurred")
    created_at: datetime = Field(..., description="Timestamp when entered in system")
    updated_at: datetime = Field(..., description="Timestamp when last modified")

    model_config = ConfigDict(populate_by_name=True)


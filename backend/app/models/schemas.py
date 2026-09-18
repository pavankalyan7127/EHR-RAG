from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# ==============================================================================
# Database Document Schemas
# ==============================================================================

class PatientDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique patient identifier, e.g. 'P001'")
    name: str = Field(..., description="Patient name or display label")
    age: Optional[int] = Field(None, description="Patient age in years")
    gender: Optional[str] = Field(None, description="Patient gender")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp in UTC")

    model_config = ConfigDict(populate_by_name=True)


class EHRRecordDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique EHR record identifier, e.g. 'ehr_P001'")
    patient_id: str = Field(..., description="Associated patient identifier, e.g. 'P001'")
    chunk_id: str = Field(..., description="Chunk ID for provenance citation, e.g. 'ehr_P001'")
    chunk_type: str = Field(default="clinical_note", description="Category or chunk type, e.g. 'clinical_note', 'medication'")
    content: str = Field(..., description="Text content of the EHR record note")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp in UTC")

    model_config = ConfigDict(populate_by_name=True)


class SessionDocument(BaseModel):
    id: str = Field(..., alias="_id", description="Unique session UUID")
    patient_id: str = Field(..., description="Identifier of the patient bound to this session")
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the message in UTC")
    sources: List[str] = Field(default_factory=list, description="List of source chunk IDs used for grounding provenance")

    model_config = ConfigDict(populate_by_name=True)


# ==============================================================================
# API Request / Response Schemas
# ==============================================================================

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Content of the message")


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Unique session identifier for multi-turn chat")
    patient_id: str = Field(..., min_length=1, description="Identifier of the patient whose record is being queried")
    message: str = Field(..., min_length=1, description="User question or query text")


class ChatResponse(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    answer: str = Field(..., description="Generated answer from the multimodal RAG assistant")
    patient_sources: List[str] = Field(default_factory=list, description="List of patient EHR chunk IDs or descriptions used")
    external_sources: List[str] = Field(default_factory=list, description="List of external knowledge chunk IDs used")
    history: List[ChatMessage] = Field(default_factory=list, description="Updated multi-turn conversation history for this session")


class VoiceChatResponse(ChatResponse):
    transcribed_text: str = Field(..., description="Transcribed query recognized by Whisper ASR")


class DeleteSessionResponse(BaseModel):
    session_id: str
    message: str
    cleared: bool


class PatientsResponse(BaseModel):
    patients: List[str] = Field(..., description="List of available patient IDs for selection")

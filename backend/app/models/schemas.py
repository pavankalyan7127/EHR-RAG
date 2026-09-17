from typing import List, Optional, Literal
from pydantic import BaseModel, Field

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

from typing import Dict, List
from app.models.schemas import ChatMessage

# In-memory storage mapping session_id -> list of ChatMessage dicts/objects
# NOTE: This is an in-memory session store suitable for local development/prototyping.
# In a distributed or production deployment, this would be replaced with Redis or PostgreSQL.
_SESSION_STORE: Dict[str, List[ChatMessage]] = {}

def get_session_history(session_id: str) -> List[ChatMessage]:
    """Retrieve conversation history for a specific session ID."""
    return _SESSION_STORE.get(session_id, [])

def add_turn_to_session(session_id: str, user_message: str, assistant_message: str) -> List[ChatMessage]:
    """Append a user-assistant turn to the session history and return the full history."""
    if session_id not in _SESSION_STORE:
        _SESSION_STORE[session_id] = []
    
    _SESSION_STORE[session_id].append(ChatMessage(role="user", content=user_message))
    _SESSION_STORE[session_id].append(ChatMessage(role="assistant", content=assistant_message))
    return _SESSION_STORE[session_id]

def clear_session_history(session_id: str) -> bool:
    """Clear conversation history for a given session ID."""
    if session_id in _SESSION_STORE:
        del _SESSION_STORE[session_id]
        return True
    return False

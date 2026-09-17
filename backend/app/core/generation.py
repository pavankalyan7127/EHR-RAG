import logging
from typing import List, Optional
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, GEMINI_MODEL_NAME
from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None

def get_genai_client() -> genai.Client:
    """Returns initialized GenAI client using the google-genai SDK."""
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. Gemini API calls will fail unless configured.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client

SYSTEM_INSTRUCTION = """You are a helpful, professional, and empathetic Multimodal EHR & Medical Question Answering Assistant.
You assist patients in understanding their electronic health records (EHR) and general medical questions.

CRITICAL GROUNDING & SAFETY GUIDELINES:
1. ONLY use facts directly stated in the PROVIDED RETRIEVED CONTEXT (Patient EHR Record and External Medical Knowledge Base).
2. NEVER hallucinate, extrapolate beyond given facts, or assume medical information not present in the context.
3. If the provided context does NOT contain enough information to answer the question, explicitly state that you do not have enough information in the medical records or reference base rather than guessing or fabricating.
4. Always clearly specify whether your answer (or parts of your answer) is derived from the Patient's personal EHR record, the external general medical knowledge base, or both.
5. Clarify that you are an AI assistant providing informational explanations, not a replacement for a direct consultation with their primary care physician.
6. CONVERSATION HISTORY NOTE: The conversation history is provided solely for conversational flow (e.g. resolving pronouns, understanding context of follow-up questions). You must NOT treat conversation history as a source of verified medical facts; all medical grounding must come strictly from the RETRIEVED CONTEXT block."""

def build_conversation_prompt(
    context_block: str,
    history: List[ChatMessage],
    new_message: str
) -> str:
    """
    Constructs the structured prompt containing context, conversation history, and current question.
    """
    prompt_sections = []

    # Section 1: Grounded Medical Context
    prompt_sections.append("### RETRIEVED MEDICAL CONTEXT (GROUND TRUTH):")
    prompt_sections.append(context_block)
    prompt_sections.append("-" * 50)

    # Section 2: Conversation History
    prompt_sections.append("### CONVERSATION HISTORY (For conversational context only, not factual grounding):")
    if history:
        for msg in history:
            role_prefix = "Patient" if msg.role == "user" else "Assistant"
            prompt_sections.append(f"{role_prefix}: {msg.content}")
    else:
        prompt_sections.append("[No previous conversation history]")
    prompt_sections.append("-" * 50)

    # Section 3: Current Question
    prompt_sections.append("### CURRENT PATIENT QUESTION:")
    prompt_sections.append(new_message.strip())
    prompt_sections.append("\n### ASSISTANT ANSWER (Grounded strictly on the retrieved context above):")

    return "\n\n".join(prompt_sections)

def generate_answer(
    context_block: str,
    history: List[ChatMessage],
    message: str
) -> str:
    """
    Calls Google Gemini API using google-genai SDK to generate a grounded response.
    """
    client = get_genai_client()
    full_prompt = build_conversation_prompt(context_block, history, message)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
            )
        )
        return response.text.strip() if response.text else "I could not generate a response based on the provided records."
    except Exception as e:
        logger.error(f"Error calling Gemini API: {str(e)}", exc_info=True)
        raise RuntimeError(f"Gemini API Error: {str(e)}")

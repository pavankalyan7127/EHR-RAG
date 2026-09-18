import os
import time
import logging
from typing import List, Optional
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, GEMINI_MODEL_NAME
from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)

# Configurable default history window (number of most recent ChatMessage objects sent to Gemini)
DEFAULT_HISTORY_WINDOW = int(os.getenv("CONVERSATION_HISTORY_WINDOW", "6"))

class GeminiQuotaExhaustedError(RuntimeError):
    """Raised when Gemini API quota, billing allocation, or prepaid credits are depleted."""
    pass

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

def is_quota_exhausted(err_str: str) -> bool:
    """
    Checks if the error represents permanent quota exhaustion / billing depletion
    (which should NOT be retried) versus a transient rate limit spike.
    """
    err_lower = err_str.lower()
    quota_indicators = [
        "resource_exhausted",
        "prepayment credits depleted",
        "prepayment",
        "quota exceeded",
        "insufficient_quota",
        "billing",
        "credit balance",
        "free tier",
        "exceeded your current quota",
        "quota has been exhausted",
        "check your plan and billing",
    ]
    return any(indicator in err_lower for indicator in quota_indicators)

def build_conversation_prompt(
    context_block: str,
    history: List[ChatMessage],
    new_message: str,
    max_history: int = DEFAULT_HISTORY_WINDOW
) -> str:
    """
    Constructs the structured prompt containing context, recent conversation history window,
    and current question.

    NOTE ON TOKEN OPTIMIZATION:
    Full conversation history remains permanently preserved in MongoDB.
    Only the most recent `max_history` messages are passed to the Gemini prompt to control
    input context size and token costs.
    """
    prompt_sections = []

    # Section 1: Grounded Medical Context
    prompt_sections.append("### RETRIEVED MEDICAL CONTEXT (GROUND TRUTH):")
    prompt_sections.append(context_block)
    prompt_sections.append("-" * 50)

    # Section 2: Conversation History (Windowed)
    prompt_sections.append("### CONVERSATION HISTORY (For conversational context only, not factual grounding):")
    effective_history = (
        history[-max_history:]
        if (max_history and max_history > 0 and len(history) > max_history)
        else history
    )

    if effective_history:
        for msg in effective_history:
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
    message: str,
    max_retries: int = 3,
    max_history: int = DEFAULT_HISTORY_WINDOW,
    patient_chunks_count: Optional[int] = None,
    external_chunks_count: Optional[int] = None
) -> str:
    """
    Calls Google Gemini API using google-genai SDK to generate a grounded response.
    - Limits conversation history passed in the prompt to `max_history` messages.
    - Logs context metrics (chunk counts, history messages, characters, estimated tokens).
    - Differentiates permanent quota exhaustion (no retries) from transient 503/429 spikes (backoff retries).
    """
    client = get_genai_client()
    full_prompt = build_conversation_prompt(
        context_block=context_block,
        history=history,
        new_message=message,
        max_history=max_history
    )

    # Request Context Monitoring:
    # Character count and approximate BPE token estimation (~4 chars/token).
    # Never log sensitive patient information or prompt text.
    prompt_chars = len(full_prompt)
    estimated_tokens = (prompt_chars + 3) // 4
    effective_history_count = min(len(history), max_history) if max_history and max_history > 0 else len(history)

    logger.info(
        f"Gemini Request Context Metrics: "
        f"patient_ehr_chunks={patient_chunks_count if patient_chunks_count is not None else 'N/A'}, "
        f"external_chunks={external_chunks_count if external_chunks_count is not None else 'N/A'}, "
        f"history_messages_included={effective_history_count} (total_stored={len(history)}), "
        f"prompt_chars={prompt_chars}, estimated_tokens={estimated_tokens}"
    )

    for attempt in range(max_retries):
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
            err_str = str(e)

            # Check for permanent quota exhaustion / depleted credits
            if is_quota_exhausted(err_str):
                logger.error(
                    f"Gemini API quota/credits exhausted. Permanent failure, aborting retries: {err_str}"
                )
                raise GeminiQuotaExhaustedError(
                    "Gemini API quota or prepaid credits have been exhausted. Please verify billing and quota limits."
                )

            # Check for transient errors suitable for retry (503, UNAVAILABLE, or temporary rate limit)
            err_lower = err_str.lower()
            is_transient = "503" in err_str or "unavailable" in err_lower or ("429" in err_str and not is_quota_exhausted(err_str))

            if is_transient and attempt < max_retries - 1:
                sleep_time = (attempt + 1) * 2
                logger.warning(
                    f"Gemini API transient error (attempt {attempt + 1}/{max_retries}): {err_str}. "
                    f"Retrying in {sleep_time}s..."
                )
                time.sleep(sleep_time)
                continue

            logger.error(f"Error calling Gemini API: {err_str}", exc_info=True)
            raise RuntimeError(f"Gemini API Error: {err_str}")

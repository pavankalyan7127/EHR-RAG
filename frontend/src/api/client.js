/**
 * API Client Module for Multimodal EHR RAG Assistant Backend
 * All network calls to the backend are encapsulated in this module.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Helper to handle HTTP responses and extract JSON or descriptive error messages.
 */
async function handleResponse(response) {
  if (!response.ok) {
    let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData && errorData.detail) {
        errorMessage = typeof errorData.detail === 'string' 
          ? errorData.detail 
          : JSON.stringify(errorData.detail);
      }
    } catch {
      // If response body is not JSON, use the status text
    }
    throw new Error(errorMessage);
  }
  return await response.json();
}

/**
 * 1. GET /patients
 * Fetches the list of all registered patient IDs in the EHR database.
 * @returns {Promise<{ patients: string[] }>}
 */
export async function getPatients() {
  const response = await fetch(`${API_BASE_URL}/patients`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });
  return handleResponse(response);
}

/**
 * 2. POST /chat
 * Sends a text query with session and patient context to the RAG pipeline.
 * @param {Object} params
 * @param {string} params.sessionId - Current multi-turn session UUID
 * @param {string} params.patientId - Patient identifier (e.g. 'P001')
 * @param {string} params.message - User question text
 * @returns {Promise<{
 *   session_id: string,
 *   answer: string,
 *   patient_sources: string[],
 *   external_sources: string[],
 *   history: Array<{ role: 'user'|'assistant', content: string }>
 * }>}
 */
export async function sendChatMessage({ sessionId, patientId, message }) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify({
      session_id: sessionId,
      patient_id: patientId,
      message: message.trim(),
    }),
  });
  return handleResponse(response);
}

/**
 * 3. POST /voice-chat
 * Sends an audio file (via multipart/form-data) for speech-to-text transcription + RAG answer.
 * @param {Object} params
 * @param {string} params.sessionId - Current multi-turn session UUID
 * @param {string} params.patientId - Patient identifier (e.g. 'P001')
 * @param {File|Blob} params.audioBlob - Recorded or uploaded audio file
 * @param {string} [params.filename] - Optional filename for the audio upload
 * @returns {Promise<{
 *   session_id: string,
 *   transcribed_text: string,
 *   answer: string,
 *   patient_sources: string[],
 *   external_sources: string[],
 *   history: Array<{ role: 'user'|'assistant', content: string }>
 * }>}
 */
export async function sendVoiceChatMessage({ sessionId, patientId, audioBlob, filename = 'voice_query.wav' }) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('patient_id', patientId);
  formData.append('audio', audioBlob, filename);

  const response = await fetch(`${API_BASE_URL}/voice-chat`, {
    method: 'POST',
    body: formData,
    // Note: Fetch automatically sets the multipart/form-data boundary when passing FormData
  });
  return handleResponse(response);
}

/**
 * 4. DELETE /chat/{session_id}
 * Resets/clears conversation history on the backend for the given session ID.
 * @param {string} sessionId
 * @returns {Promise<{ session_id: string, message: string, cleared: boolean }>}
 */
export async function clearSessionHistory(sessionId) {
  const response = await fetch(`${API_BASE_URL}/chat/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: {
      'Accept': 'application/json',
    },
  });
  return handleResponse(response);
}

/**
 * API Client Module for Multimodal EHR RAG Assistant Backend
 * Handles patient authentication, session management, and RAG chat interactions.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const TOKEN_KEY = 'ehr_access_token';
const PATIENT_ID_KEY = 'ehr_patient_id';
const ROLE_KEY = 'ehr_user_role';

/**
 * Token & Session Storage Helpers
 */
export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUserRole() {
  return localStorage.getItem(ROLE_KEY) || 'patient';
}

export function isAdmin() {
  return getUserRole() === 'admin';
}

export function setAuthSession(token, patientId, role = 'patient') {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  if (patientId) localStorage.setItem(PATIENT_ID_KEY, patientId);
  if (role) localStorage.setItem(ROLE_KEY, role);
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PATIENT_ID_KEY);
  localStorage.removeItem(ROLE_KEY);
}

export function getStoredPatientId() {
  return localStorage.getItem(PATIENT_ID_KEY);
}

export function isAuthenticated() {
  return Boolean(getAuthToken());
}

/**
 * Builds request headers with JWT Bearer token when authenticated
 */
function getAuthHeaders(contentType = 'application/json') {
  const headers = {
    'Accept': 'application/json',
  };
  if (contentType) {
    headers['Content-Type'] = contentType;
  }
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Response Handler with error extraction and 401 interceptor
 */
async function handleResponse(response) {
  if (!response.ok) {
    if (response.status === 401) {
      clearAuthSession();
      window.dispatchEvent(new CustomEvent('ehr-auth-expired'));
    }

    let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData && errorData.detail) {
        errorMessage = typeof errorData.detail === 'string'
          ? errorData.detail
          : JSON.stringify(errorData.detail);
      }
    } catch {
      // Body not JSON
    }
    throw new Error(errorMessage);
  }
  return await response.json();
}

/**
 * =============================================================================
 * Authentication API
 * =============================================================================
 */

/**
 * Authenticates a patient with patient_id and password.
 * @param {Object} credentials
 * @param {string} credentials.patientId
 * @param {string} credentials.password
 * @returns {Promise<{ access_token: string, token_type: string, patient_id: string }>}
 */
export async function login({ patientId, password }) {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify({
      patient_id: patientId.trim(),
      password: password,
    }),
  });

  const data = await handleResponse(response);
  setAuthSession(data.access_token, data.patient_id, data.role || 'patient');
  return data;
}

/**
 * Fetches the authenticated patient's profile.
 * @returns {Promise<{ patient_id: string, name: string, age: number|null, gender: string|null }>}
 */
export async function getPatientProfile() {
  const response = await fetch(`${API_BASE_URL}/patients/me`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * =============================================================================
 * Session History API (Patient-Isolated)
 * =============================================================================
 */

/**
 * Fetches all chat sessions belonging strictly to the authenticated patient.
 * @returns {Promise<Array<{ session_id: string, patient_id: string, title: string, created_at: string, updated_at: string }>>}
 */
export async function getChatSessions() {
  const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Creates a new chat session for the authenticated patient.
 * @param {string} [title="New Conversation"]
 * @returns {Promise<{ session_id: string, patient_id: string, title: string, created_at: string, updated_at: string }>}
 */
export async function createChatSession(title = 'New Conversation') {
  const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ title }),
  });
  return handleResponse(response);
}

/**
 * Retrieves the full message history for a specific session ID belonging to the authenticated patient.
 * @param {string} sessionId
 * @returns {Promise<{ session_id: string, patient_id: string, title: string, messages: Array<{ role: string, content: string, sources?: string[] }> }>}
 */
export async function getSessionDetails(sessionId) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Deletes a chat session and all its messages.
 * @param {string} sessionId
 * @returns {Promise<{ session_id: string, message: string, cleared: boolean }>}
 */
export async function deleteChatSession(sessionId) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * =============================================================================
 * Chat & Voice API
 * =============================================================================
 */

/**
 * Sends a text query with session ID to the RAG pipeline.
 * Patient identity is derived strictly by the backend from the JWT.
 * @param {Object} params
 * @param {string} params.sessionId
 * @param {string} params.message
 * @returns {Promise<{
 *   session_id: string,
 *   answer: string,
 *   patient_sources: string[],
 *   external_sources: string[],
 *   history: Array<{ role: 'user'|'assistant', content: string }>
 * }>}
 */
export async function sendChatMessage({ sessionId, message }) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      session_id: sessionId,
      message: message.trim(),
    }),
  });
  return handleResponse(response);
}

/**
 * Sends an audio file for speech-to-text transcription + RAG answer.
 * Patient identity is derived strictly by the backend from the JWT.
 * @param {Object} params
 * @param {string} params.sessionId
 * @param {File|Blob} params.audioBlob
 * @param {string} [params.filename]
 */
export async function sendVoiceChatMessage({ sessionId, audioBlob, filename = 'voice_query.wav' }) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('audio', audioBlob, filename);

  const token = getAuthToken();
  const headers = {
    'Accept': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}/voice-chat`, {
    method: 'POST',
    headers: headers,
    body: formData,
  });
  return handleResponse(response);
}

/**
 * Resolves an audio URL or relative path to a full streaming URL with authentication token attached.
 * Supports native HTML5 <audio> streaming playback across sessions.
 * @param {string} audioUrl
 * @returns {string|null}
 */
export function resolveAudioUrl(audioUrl) {
  if (!audioUrl) return null;
  const token = getAuthToken();
  let fullUrl = audioUrl.startsWith('http') ? audioUrl : `${API_BASE_URL}${audioUrl.startsWith('/') ? '' : '/'}${audioUrl}`;
  if (token && !fullUrl.includes('token=')) {
    const delimiter = fullUrl.includes('?') ? '&' : '?';
    fullUrl = `${fullUrl}${delimiter}token=${encodeURIComponent(token)}`;
  }
  return fullUrl;
}

/**
 * Returns the stream URL for a specific message audio recording with authentication token attached.
 * @param {string} messageId
 * @returns {string|null}
 */
export function getMessageAudioUrl(messageId) {
  if (!messageId) return null;
  return resolveAudioUrl(`/chat/messages/${encodeURIComponent(messageId)}/audio`);
}

/**
 * =============================================================================
 * Admin Dashboard API (Role: Admin Required)
 * =============================================================================
 */

/**
 * Lists all patients in registry with record counts and account status.
 */
export async function getAdminPatients() {
  const response = await fetch(`${API_BASE_URL}/admin/patients`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Creates a new patient account with optional custom ID and password.
 */
export async function createAdminPatient(patientData) {
  const response = await fetch(`${API_BASE_URL}/admin/patients`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(patientData),
  });
  return handleResponse(response);
}

/**
 * Retrieves details for a specific patient.
 */
export async function getAdminPatientDetail(patientId) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Updates patient demographics (name, age, gender) or active status.
 */
export async function updateAdminPatient(patientId, updateData) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(updateData),
  });
  return handleResponse(response);
}

/**
 * Permanently deletes a patient and cascades cleanup (destructive).
 */
export async function deleteAdminPatient(patientId) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Retrieves all EHR records for a patient, ordered newest first.
 */
export async function getAdminPatientRecords(patientId) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}/records`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Adds a new EHR record for a patient (auto-generates monotonic sequence ID).
 */
export async function createAdminRecord(patientId, recordData) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}/records`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(recordData),
  });
  return handleResponse(response);
}

/**
 * Updates an existing EHR record.
 */
export async function updateAdminRecord(patientId, recordId, recordData) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}/records/${encodeURIComponent(recordId)}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(recordData),
  });
  return handleResponse(response);
}

/**
 * Deletes an EHR record without sequence reuse.
 */
export async function deleteAdminRecord(patientId, recordId) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}/records/${encodeURIComponent(recordId)}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}



import { useState, useCallback, useRef } from 'react';
import { sendChatMessage, sendVoiceChatMessage, clearSessionHistory } from '../api/client';

/**
 * Utility function to generate a unique session UUID for multi-turn chat sessions.
 */
function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'sess_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
}

/**
 * Custom hook to manage the full lifecycle of a continuous multi-turn chat:
 * - Maintains a persistent session_id for backend context tracking
 * - Appends user messages immediately to the chat window (optimistic UI)
 * - Appends assistant answers, source citations, and transcription tags
 * - Handles loading and error states gracefully
 */
export function useChat(selectedPatientId) {
  const [sessionId, setSessionId] = useState(() => generateUUID());
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Keep a ref to the current session ID to avoid stale closures in async handlers
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  /**
   * Resets the current chat session:
   * 1. Calls DELETE /chat/{session_id} on the backend to clear server-side memory
   * 2. Clears the local message stream
   * 3. Generates a fresh session_id
   */
  const startNewChat = useCallback(async () => {
    const oldSessionId = sessionIdRef.current;
    try {
      if (oldSessionId) {
        await clearSessionHistory(oldSessionId);
      }
    } catch (err) {
      console.warn(`Could not clear session ${oldSessionId} on backend:`, err);
    } finally {
      const newId = generateUUID();
      setSessionId(newId);
      sessionIdRef.current = newId;
      setMessages([]);
      setError(null);
    }
  }, []);

  /**
   * Sends a typed text query to the backend
   */
  const sendMessage = useCallback(async (text) => {
    if (!text || !text.trim() || !selectedPatientId || isLoading) return;

    const trimmedText = text.trim();
    setError(null);

    // 1. Optimistically append user message to local UI
    const userMsgId = 'msg_user_' + Date.now();
    const userMessageObj = {
      id: userMsgId,
      role: 'user',
      content: trimmedText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMessageObj]);
    setIsLoading(true);

    try {
      // 2. Call backend /chat endpoint
      const response = await sendChatMessage({
        sessionId: sessionIdRef.current,
        patientId: selectedPatientId,
        message: trimmedText,
      });

      // 3. Append assistant response with source metadata
      const assistantMsgObj = {
        id: 'msg_ast_' + Date.now(),
        role: 'assistant',
        content: response.answer,
        patientSources: response.patient_sources || [],
        externalSources: response.external_sources || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsgObj]);
    } catch (err) {
      console.error('Error sending message:', err);
      setError(err.message || 'Failed to send message.');

      // Append system error message bubble
      const errorMsgObj = {
        id: 'msg_err_' + Date.now(),
        role: 'system_error',
        content: `Unable to get answer: ${err.message || 'Something went wrong. Please check your backend connection.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsgObj]);
    } finally {
      setIsLoading(false);
    }
  }, [selectedPatientId, isLoading]);

  /**
   * Sends a voice query (file or recorded audio) to the backend
   */
  const sendVoiceMessage = useCallback(async (audioBlob, filename = 'voice_query.wav') => {
    if (!audioBlob || !selectedPatientId || isLoading) return;

    setError(null);
    setIsLoading(true);

    // Create a local blob URL so the user can play back their recorded audio in the chat
    const audioUrl = URL.createObjectURL(audioBlob);

    // Placeholder pending message while speech-to-text is running
    const placeholderId = 'msg_voice_pending_' + Date.now();
    const pendingMsgObj = {
      id: placeholderId,
      role: 'user',
      isVoice: true,
      audioUrl: audioUrl,
      content: '🎙️ Transcribing voice question...',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, pendingMsgObj]);

    try {
      const response = await sendVoiceChatMessage({
        sessionId: sessionIdRef.current,
        patientId: selectedPatientId,
        audioBlob,
        filename,
      });

      // Update the user's message bubble with the recognized transcription
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === placeholderId
            ? {
                ...msg,
                content: response.transcribed_text || '(Voice message)',
                isTranscribed: true,
                audioUrl: audioUrl,
              }
            : msg
        )
      );


      // Append assistant answer
      const assistantMsgObj = {
        id: 'msg_ast_' + Date.now(),
        role: 'assistant',
        content: response.answer,
        patientSources: response.patient_sources || [],
        externalSources: response.external_sources || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsgObj]);
    } catch (err) {
      console.error('Error in voice chat:', err);
      setError(err.message || 'Voice chat processing failed.');

      // Remove the pending placeholder and add an error bubble
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== placeholderId),
        {
          id: 'msg_err_' + Date.now(),
          role: 'system_error',
          content: `Voice processing error: ${err.message || 'Failed to process audio.'}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [selectedPatientId, isLoading]);

  return {
    sessionId,
    messages,
    isLoading,
    error,
    sendMessage,
    sendVoiceMessage,
    startNewChat,
  };
}

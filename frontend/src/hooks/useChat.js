import { useState, useCallback, useRef, useEffect } from 'react';
import {
  getChatSessions,
  createChatSession,
  getSessionDetails,
  deleteChatSession,
  sendChatMessage,
  sendVoiceChatMessage,
  resolveAudioUrl,
} from '../api/client';

function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'sess_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
}

export function useChat(isAuthenticated) {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState(null);

  const activeSessionIdRef = useRef(activeSessionId);
  activeSessionIdRef.current = activeSessionId;

  /**
   * Fetches all chat sessions belonging to the authenticated patient.
   */
  const loadSessionsList = useCallback(async (autoSelect = false) => {
    if (!isAuthenticated) return;
    setIsLoadingSessions(true);
    try {
      const list = await getChatSessions();
      setSessions(list || []);

      if (autoSelect) {
        if (list && list.length > 0) {
          // Select the most recently active session
          await selectSession(list[0].session_id);
        } else {
          // No existing sessions: initialize a fresh one
          await startNewChat();
        }
      }
    } catch (err) {
      console.error('Failed to load chat sessions:', err);
      setError(err.message || 'Could not retrieve conversation history.');
    } finally {
      setIsLoadingSessions(false);
    }
  }, [isAuthenticated]);

  /**
   * Selects an existing session and loads its messages from MongoDB.
   */
  const selectSession = useCallback(async (sessionId) => {
    if (!sessionId) return;
    setIsLoadingHistory(true);
    setError(null);
    try {
      const details = await getSessionDetails(sessionId);
      setActiveSessionId(sessionId);

      // Map backend messages to UI format
      const formatted = (details.messages || []).map((m, idx) => ({
        id: m.id || `msg_${sessionId}_${idx}`,
        role: m.role,
        content: m.content,
        timestamp: m.timestamp
          ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        patientSources: m.sources || [],
        externalSources: [],
        inputType: m.input_type || 'text',
        isVoice: m.input_type === 'voice' || Boolean(m.audio_file_id || m.audio_url),
        audioFileId: m.audio_file_id || null,
        audioUrl: resolveAudioUrl(m.audio_url),
      }));

      setMessages(formatted);
    } catch (err) {
      console.error(`Failed to load session ${sessionId}:`, err);
      setError(err.message || 'Could not load conversation messages.');
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  /**
   * Starts a brand new chat session and clears the conversation UI.
   */
  const startNewChat = useCallback(async () => {
    setError(null);
    try {
      const newSession = await createChatSession('New Conversation');
      setSessions((prev) => [newSession, ...prev.filter((s) => s.session_id !== newSession.session_id)]);
      setActiveSessionId(newSession.session_id);
      setMessages([]);
      return newSession.session_id;
    } catch (err) {
      console.error('Failed to create new session:', err);
      // Fallback: generate local session ID
      const fallbackId = generateUUID();
      setActiveSessionId(fallbackId);
      setMessages([]);
      return fallbackId;
    }
  }, []);

  /**
   * Deletes a session and removes it from the sidebar list.
   */
  const deleteSession = useCallback(async (sessionId) => {
    try {
      await deleteChatSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));

      if (activeSessionIdRef.current === sessionId) {
        // Active session was deleted; switch to another or new
        const remaining = sessions.filter((s) => s.session_id !== sessionId);
        if (remaining.length > 0) {
          selectSession(remaining[0].session_id);
        } else {
          startNewChat();
        }
      }
    } catch (err) {
      console.error(`Failed to delete session ${sessionId}:`, err);
      setError(err.message || 'Failed to delete conversation.');
    }
  }, [sessions, selectSession, startNewChat]);

  /**
   * Sends a text query in the current session.
   */
  const sendMessage = useCallback(async (text) => {
    if (!text || !text.trim() || isLoading) return;

    let currentId = activeSessionIdRef.current;
    if (!currentId) {
      currentId = await startNewChat();
    }

    const trimmedText = text.trim();
    setError(null);

    // 1. Optimistic UI update
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
        sessionId: currentId,
        message: trimmedText,
      });

      // 3. Append assistant response
      const assistantMsgObj = {
        id: 'msg_ast_' + Date.now(),
        role: 'assistant',
        content: response.answer,
        patientSources: response.patient_sources || [],
        externalSources: response.external_sources || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsgObj]);

      // 4. Refresh session list so auto-generated title and updated_at sync in sidebar
      loadSessionsList(false);
    } catch (err) {
      console.error('Error sending message:', err);
      setError(err.message || 'Failed to send message.');

      const errorMsgObj = {
        id: 'msg_err_' + Date.now(),
        role: 'system_error',
        content: `Unable to get answer: ${err.message || 'Something went wrong.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsgObj]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, startNewChat, loadSessionsList]);

  /**
   * Sends a recorded voice query in the current session.
   */
  const sendVoiceMessage = useCallback(async (audioBlob, filename = 'voice_query.wav') => {
    if (!audioBlob || isLoading) return;

    let currentId = activeSessionIdRef.current;
    if (!currentId) {
      currentId = await startNewChat();
    }

    setError(null);
    setIsLoading(true);

    const audioUrl = URL.createObjectURL(audioBlob);
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
        sessionId: currentId,
        audioBlob,
        filename,
      });

      const serverAudioUrl = resolveAudioUrl(response.audio_url);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === placeholderId
            ? {
                ...msg,
                content: response.transcribed_text || '(Voice message)',
                isTranscribed: true,
                audioUrl: serverAudioUrl || audioUrl,
                audioFileId: response.audio_file_id || null,
                inputType: 'voice',
                isVoice: true,
              }
            : msg
        )
      );

      const assistantMsgObj = {
        id: 'msg_ast_' + Date.now(),
        role: 'assistant',
        content: response.answer,
        patientSources: response.patient_sources || [],
        externalSources: response.external_sources || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsgObj]);

      loadSessionsList(false);
    } catch (err) {
      console.error('Error in voice chat:', err);
      setError(err.message || 'Voice chat processing failed.');

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
  }, [isLoading, startNewChat, loadSessionsList]);

  // Initial load when user becomes authenticated
  useEffect(() => {
    if (isAuthenticated) {
      loadSessionsList(true);
    } else {
      setSessions([]);
      setActiveSessionId(null);
      setMessages([]);
    }
  }, [isAuthenticated, loadSessionsList]);

  return {
    sessions,
    activeSessionId,
    messages,
    isLoading,
    isLoadingSessions,
    isLoadingHistory,
    error,
    loadSessionsList,
    selectSession,
    startNewChat,
    deleteSession,
    sendMessage,
    sendVoiceMessage,
  };
}

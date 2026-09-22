import { useState, useCallback, useRef, useEffect } from 'react';
import {
  getChatSessions,
  createChatSession,
  getSessionDetails,
  deleteChatSession,
  sendChatMessage,
  sendVoiceChatMessage,
  localizeChatMessage,
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
  const [selectedLanguage, setSelectedLanguage] = useState('en');
  const [localizingMessageId, setLocalizingMessageId] = useState(null);
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
        canonicalAnswer: m.canonical_answer || null,
        language: m.language || null,
        audioBase64: m.audio_base64 || null,
        audioFormat: m.audio_format || null,
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
      // 2. Call backend /chat endpoint with targetLanguage
      const response = await sendChatMessage({
        sessionId: currentId,
        message: trimmedText,
        targetLanguage: selectedLanguage,
      });

      // 3. Append assistant response with multilingual fields
      const assistantMsgObj = {
        id: 'msg_ast_' + Date.now(),
        role: 'assistant',
        content: response.answer,
        canonicalAnswer: response.canonical_answer || response.answer,
        language: response.language || selectedLanguage,
        audioBase64: response.audio_base64 || null,
        audioFormat: response.audio_format || null,
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
  }, [isLoading, startNewChat, loadSessionsList, selectedLanguage]);

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
        targetLanguage: selectedLanguage,
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
        canonicalAnswer: response.canonical_answer || response.answer,
        language: response.language || selectedLanguage,
        audioBase64: response.audio_base64 || null,
        audioFormat: response.audio_format || null,
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
  }, [isLoading, startNewChat, loadSessionsList, selectedLanguage]);

  /**
   * Switches the language of an existing assistant response without rerunning medical reasoning.
   */
  const switchMessageLanguage = useCallback(
    async (messageId, targetLanguage) => {
      if (!messageId || !targetLanguage) return;

      // A. Find the assistant message with message.id === messageId
      const targetMsg = messages.find((m) => m.id === messageId && m.role === 'assistant');

      // B. If it does not exist, return without making an API request
      if (!targetMsg) return;

      // C. Get the canonical English answer
      const englishAnswer = targetMsg.canonicalAnswer;

      // D. If canonicalAnswer is missing, do not call the API. Preserve the current message.
      if (!englishAnswer) return;

      if (localizingMessageId === messageId) return;

      setLocalizingMessageId(messageId);
      setError(null);

      try {
        // E. Call localizeChatMessage
        const response = await localizeChatMessage({
          englishResponse: englishAnswer,
          targetLanguage,
        });

        // G. Update ONLY the matching message in the messages state
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  content: response.native_text,
                  language: response.target_language || targetLanguage,
                  audioBase64: response.audio_base64 || null,
                  audioFormat: response.audio_format || null,
                }
              : msg
          )
        );
      } catch (err) {
        console.error(`Failed to localize message ${messageId}:`, err);
        setError(err.message || 'Failed to switch language.');
      } finally {
        setLocalizingMessageId(null);
      }
    },
    [messages, localizingMessageId]
  );

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
    selectedLanguage,
    setSelectedLanguage,
    localizingMessageId,
    switchMessageLanguage,
    loadSessionsList,
    selectSession,
    startNewChat,
    deleteSession,
    sendMessage,
    sendVoiceMessage,
  };
}

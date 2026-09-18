import React, { useState, useEffect, useCallback } from 'react';
import {
  getAuthToken,
  getStoredPatientId,
  clearAuthSession,
  getPatientProfile,
} from './api/client';
import { useChat } from './hooks/useChat';
import { Login } from './components/Login';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ChatWindow } from './components/ChatWindow';
import { InputBar } from './components/InputBar';
import './styles/App.css';

export function App() {
  const [token, setToken] = useState(() => getAuthToken());
  const [patientId, setPatientId] = useState(() => getStoredPatientId());
  const [patientProfile, setPatientProfile] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const isAuthenticated = Boolean(token && patientId);

  // Initialize patient-isolated chat lifecycle hook
  const {
    sessions,
    activeSessionId,
    messages,
    isLoading,
    isLoadingSessions,
    isLoadingHistory,
    selectSession,
    startNewChat,
    deleteSession,
    sendMessage,
    sendVoiceMessage,
  } = useChat(isAuthenticated);

  const handleLogout = useCallback(() => {
    clearAuthSession();
    setToken(null);
    setPatientId(null);
    setPatientProfile(null);
  }, []);

  // Fetch patient profile when authenticated
  useEffect(() => {
    if (token) {
      getPatientProfile()
        .then((profile) => {
          setPatientProfile(profile);
          setPatientId(profile.patient_id);
        })
        .catch((err) => {
          console.warn('Session verification failed:', err);
          handleLogout();
        });
    }
  }, [token, handleLogout]);

  // Listen for auth expiration events from API client
  useEffect(() => {
    const onAuthExpired = () => {
      handleLogout();
    };
    window.addEventListener('ehr-auth-expired', onAuthExpired);
    return () => window.removeEventListener('ehr-auth-expired', onAuthExpired);
  }, [handleLogout]);

  const handleLoginSuccess = (newPatientId) => {
    const newToken = getAuthToken();
    setToken(newToken);
    setPatientId(newPatientId);
  };

  // If unauthenticated: render dedicated hospital portal login screen
  if (!isAuthenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="portal-app">
      {/* Top Application Header with Patient Identity & Logout */}
      <Header
        patientProfile={patientProfile}
        patientId={patientId}
        onLogout={handleLogout}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        isSidebarOpen={isSidebarOpen}
      />

      {/* Main Two-Pane Dashboard: Sidebar (Left) + Chat Window & Input (Right) */}
      <div className="portal-body">
        <Sidebar
          patientId={patientId}
          sessions={sessions}
          activeSessionId={activeSessionId}
          isLoadingSessions={isLoadingSessions}
          onSelectSession={selectSession}
          onNewChat={startNewChat}
          onDeleteSession={deleteSession}
          isOpen={isSidebarOpen}
        />

        <div className="portal-chat-area">
          <ChatWindow
            messages={messages}
            isLoading={isLoading || isLoadingHistory}
            selectedPatient={patientId}
            onSelectSuggestedQuestion={(q) => sendMessage(q)}
          />

          <InputBar
            onSendMessage={sendMessage}
            onSendVoiceMessage={sendVoiceMessage}
            isLoading={isLoading}
            disabled={isLoading || isLoadingHistory}
          />
        </div>
      </div>
    </div>
  );
}

export default App;

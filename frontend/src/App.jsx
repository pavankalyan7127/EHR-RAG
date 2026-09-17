import React, { useState, useEffect } from 'react';
import { getPatients } from './api/client';
import { useChat } from './hooks/useChat';
import { PatientSelector } from './components/PatientSelector';
import { ChatWindow } from './components/ChatWindow';
import { InputBar } from './components/InputBar';
import './styles/App.css';

export function App() {
  const [patients, setPatients] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState('');
  const [isLoadingPatients, setIsLoadingPatients] = useState(true);
  const [patientError, setPatientError] = useState(null);

  // Initialize continuous multi-turn chat hook bound to selected patient
  const {
    sessionId,
    messages,
    isLoading,
    sendMessage,
    sendVoiceMessage,
    startNewChat,
  } = useChat(selectedPatient);

  // Fetch available patients on initial component mount
  const fetchPatientsList = async () => {
    setIsLoadingPatients(true);
    setPatientError(null);
    try {
      const data = await getPatients();
      const patientList = data.patients || [];
      setPatients(patientList);
      if (patientList.length > 0 && !selectedPatient) {
        setSelectedPatient(patientList[0]);
      }
    } catch (err) {
      console.error('Failed to load patients:', err);
      setPatientError(err.message || 'Could not connect to EHR backend.');
    } finally {
      setIsLoadingPatients(false);
    }
  };

  useEffect(() => {
    fetchPatientsList();
  }, []);

  // When patient selection changes, reset chat session so contexts do not bleed
  const handleSelectPatient = (patientId) => {
    if (patientId !== selectedPatient) {
      setSelectedPatient(patientId);
      startNewChat();
    }
  };

  return (
    <div className="app-layout">
      {/* Top Navigation & Patient Selector */}
      <PatientSelector
        patients={patients}
        selectedPatient={selectedPatient}
        onSelectPatient={handleSelectPatient}
        onNewChat={startNewChat}
        isLoadingPatients={isLoadingPatients}
        patientError={patientError}
        onRetryFetchPatients={fetchPatientsList}
      />

      {/* Main Continuous Chat Viewport */}
      <ChatWindow
        messages={messages}
        isLoading={isLoading}
        selectedPatient={selectedPatient}
        onSelectSuggestedQuestion={(q) => sendMessage(q)}
      />

      {/* Bottom Sticky Input Bar */}
      <InputBar
        onSendMessage={sendMessage}
        onSendVoiceMessage={sendVoiceMessage}
        isLoading={isLoading}
        disabled={!selectedPatient || isLoadingPatients}
      />
    </div>
  );
}

export default App;

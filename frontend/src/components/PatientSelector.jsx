import React from 'react';

/**
 * PatientSelector Component
 * Allows selecting a patient ID from the backend EHR database.
 * Displays connection status and triggers session refresh on patient change.
 */
export function PatientSelector({
  patients,
  selectedPatient,
  onSelectPatient,
  onNewChat,
  isLoadingPatients,
  patientError,
  onRetryFetchPatients,
}) {
  return (
    <header className="app-header">
      <div className="header-left">
        <div className="logo-badge">
          <span className="logo-icon">🩺</span>
          <div className="logo-text">
            <h1>EHR Assistant</h1>
            <span className="subtitle">Multimodal Clinical RAG</span>
          </div>
        </div>
      </div>

      <div className="header-controls">
        <div className="patient-selector-wrapper">
          <label htmlFor="patient-select" className="selector-label">
            Active Patient:
          </label>
          {isLoadingPatients ? (
            <div className="selector-loading">Loading records...</div>
          ) : patientError ? (
            <div className="selector-error">
              <span>Failed to load</span>
              <button className="btn-retry" onClick={onRetryFetchPatients} title="Retry loading patients">
                ↻ Retry
              </button>
            </div>
          ) : (
            <div className="custom-select-container">
              <select
                id="patient-select"
                className="patient-select"
                value={selectedPatient || ''}
                onChange={(e) => onSelectPatient(e.target.value)}
              >
                {patients.length === 0 && <option value="">No Patients Found</option>}
                {patients.map((pid) => (
                  <option key={pid} value={pid}>
                    Patient {pid}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <button
          className="btn-new-chat"
          onClick={onNewChat}
          title="Start a new conversation and clear context"
        >
          <span className="btn-icon">✨</span>
          <span>New Chat</span>
        </button>
      </div>
    </header>
  );
}

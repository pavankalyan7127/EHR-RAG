import React from 'react';

export function Header({ patientProfile, patientId, onLogout, onToggleSidebar, isSidebarOpen }) {
  const displayName = patientProfile?.name || `Patient ${patientId}`;

  return (
    <header className="app-header">
      <div className="header-left">
        <button
          className="sidebar-toggle-btn"
          onClick={onToggleSidebar}
          title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
          aria-label="Toggle chat history sidebar"
        >
          <span className="toggle-icon">☰</span>
        </button>

        <div className="logo-badge">
          <span className="logo-icon">🩺</span>
          <div className="logo-text">
            <h1>EHR Assistant</h1>
            <span className="subtitle">Clinical Portal & RAG</span>
          </div>
        </div>
      </div>

      <div className="header-right">
        <div className="patient-status-badge">
          <span className="status-indicator"></span>
          <div className="patient-meta">
            <span className="patient-name">{displayName}</span>
            <span className="patient-id-tag">ID: {patientId}</span>
          </div>
        </div>

        <button
          className="btn-logout"
          onClick={onLogout}
          title="Sign out of patient portal"
        >
          <span className="btn-icon">🚪</span>
          <span>Logout</span>
        </button>
      </div>
    </header>
  );
}

export default Header;

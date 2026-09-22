import React from 'react';

export function Header({
  patientProfile,
  patientId,
  onLogout,
  onToggleSidebar,
  isSidebarOpen,
  selectedLanguage = 'en',
  setSelectedLanguage = () => {},
}) {
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

        <div className="header-language-selector">
          <label htmlFor="header-language-select" className="header-language-label">
            Language
          </label>
          <select
            id="header-language-select"
            className="header-language-select"
            value={selectedLanguage}
            onChange={(e) => setSelectedLanguage(e.target.value)}
            aria-label="Select conversation language"
          >
            <option value="en">English</option>
            <option value="bn">বাংলা</option>
            <option value="gu">ગુજરાતી</option>
            <option value="hi">हिन्दी</option>
            <option value="mr">मराठी</option>
            <option value="pa">ਪੰਜਾਬੀ</option>
            <option value="ta">தமிழ்</option>
            <option value="te">తెలుగు</option>
            <option value="ur">اردو</option>
          </select>
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

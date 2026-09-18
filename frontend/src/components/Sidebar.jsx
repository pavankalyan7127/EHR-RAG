import React from 'react';

/**
 * Helper to format ISO timestamps into user-friendly hospital timeline labels.
 */
function formatSessionTime(timestampStr) {
  if (!timestampStr) return '';
  const date = new Date(timestampStr);
  const now = new Date();

  const isToday =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    date.getDate() === yesterday.getDate() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getFullYear() === yesterday.getFullYear();

  const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (isToday) return `Today, ${timeStr}`;
  if (isYesterday) return `Yesterday, ${timeStr}`;
  return `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${timeStr}`;
}

export function Sidebar({
  patientId,
  sessions,
  activeSessionId,
  isLoadingSessions,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  isOpen,
}) {
  return (
    <aside className={`chat-sidebar ${isOpen ? 'open' : 'closed'}`}>
      {/* Patient Header Badge */}
      <div className="sidebar-patient-card">
        <div className="patient-avatar-badge">👤</div>
        <div className="patient-details">
          <span className="sidebar-patient-label">Active Patient</span>
          <span className="sidebar-patient-id">{patientId}</span>
        </div>
      </div>

      {/* New Chat Action */}
      <div className="sidebar-action-container">
        <button
          className="btn-sidebar-new-chat"
          onClick={onNewChat}
          title="Start a fresh chat session"
        >
          <span className="btn-icon">➕</span>
          <span>New Chat</span>
        </button>
      </div>

      {/* Chat History Section */}
      <div className="sidebar-history-section">
        <div className="history-header">
          <span className="history-title">CHAT HISTORY</span>
          {sessions.length > 0 && (
            <span className="history-count">{sessions.length}</span>
          )}
        </div>

        <div className="history-list">
          {isLoadingSessions && sessions.length === 0 ? (
            <div className="history-loading">
              <div className="spinner-mini"></div>
              <span>Loading conversations...</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="history-empty">
              <span className="empty-chat-icon">💬</span>
              <p>No saved conversations</p>
              <span className="empty-subtext">Click + New Chat to start</span>
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = session.session_id === activeSessionId;
              return (
                <div
                  key={session.session_id}
                  className={`history-item ${isActive ? 'active' : ''}`}
                  onClick={() => onSelectSession(session.session_id)}
                  title={session.title || 'Conversation'}
                >
                  <div className="item-icon">💬</div>
                  <div className="item-content">
                    <span className="item-title">
                      {session.title || 'New Conversation'}
                    </span>
                    <span className="item-time">
                      {formatSessionTime(session.updated_at || session.created_at)}
                    </span>
                  </div>

                  {onDeleteSession && (
                    <button
                      className="btn-delete-session"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteSession(session.session_id);
                      }}
                      title="Delete this conversation"
                      aria-label="Delete session"
                    >
                      🗑️
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;

import React, { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';

/**
 * ChatWindow Component
 * Scrollable viewport for continuous multi-turn dialogue with auto-scroll and empty states.
 */
export function ChatWindow({
  messages,
  isLoading,
  selectedPatient,
  onSelectSuggestedQuestion,
  switchMessageLanguage,
  localizingMessageId,
}) {
  const scrollEndRef = useRef(null);

  // Auto-scroll to the bottom when new messages arrive or loading state changes
  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const sampleQuestions = [
    'What medications am I currently prescribed?',
    'What was my most recent test result or HbA1c level?',
    'Do I have any documented drug allergies?',
    'What are the common symptoms of my condition?',
  ];

  return (
    <main className="chat-window">
      {messages.length === 0 ? (
        <div className="chat-empty-state">
          <div className="empty-icon-circle">
            <span className="empty-icon">🩺</span>
          </div>
          <h2>Personalized EHR Medical Assistant</h2>
          <p className="empty-subtitle">
            Ask questions about Patient <strong>{selectedPatient || '...'}</strong>'s health records, medications, and general medical conditions.
          </p>

          <div className="suggested-questions-card">
            <h3>Suggested Questions</h3>
            <div className="suggested-chips">
              {sampleQuestions.map((q, idx) => (
                <button
                  key={idx}
                  className="suggested-chip"
                  onClick={() => onSelectSuggestedQuestion && onSelectSuggestedQuestion(q)}
                >
                  💬 {q}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="messages-list">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onSwitchLanguage={switchMessageLanguage}
              localizingMessageId={localizingMessageId}
            />
          ))}

          {/* Typing / Processing Indicator */}
          {isLoading && (
            <div className="message-row assistant-row">
              <div className="message-avatar">🤖</div>
              <div className="typing-indicator-bubble">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
            </div>
          )}

          <div ref={scrollEndRef} />
        </div>
      )}
    </main>
  );
}

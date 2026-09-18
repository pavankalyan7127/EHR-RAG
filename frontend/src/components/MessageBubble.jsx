import React, { useState } from 'react';

/**
 * MessageBubble Component
 * Renders user, assistant, or system error message bubbles.
 * Features collapsible source attribution tags for groundedness transparency.
 */
export function MessageBubble({ message }) {
  const [showSources, setShowSources] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  const { role, content, timestamp, patientSources, externalSources } = message;
  const isVoice = message.isVoice || message.inputType === 'voice' || Boolean(message.audioUrl || message.audioFileId);

  // System error bubble
  if (role === 'system_error') {
    return (
      <div className="message-row system-error-row">
        <div className="system-error-bubble">
          <span className="error-icon">⚠️</span>
          <span className="error-text">{content}</span>
        </div>
      </div>
    );
  }

  const isUser = role === 'user';
  const hasSources = (patientSources && patientSources.length > 0) || (externalSources && externalSources.length > 0);

  // Text-to-Speech Controller for AI Assistant Answers
  const handlePlayTTS = () => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      alert('Text-to-speech is not supported in this browser.');
      return;
    }

    // If currently speaking and paused, resume
    if (isSpeaking && isPaused) {
      window.speechSynthesis.resume();
      setIsPaused(false);
      return;
    }

    // If speaking, pause it
    if (isSpeaking && !isPaused) {
      window.speechSynthesis.pause();
      setIsPaused(true);
      return;
    }

    // Cancel any ongoing speech and speak this message
    window.speechSynthesis.cancel();

    // Clean text of markdown asterisks/symbols for natural speech
    const cleanSpeechText = content
      .replace(/[*_#`~[\]]/g, '')
      .replace(/https?:\/\/\S+/g, 'link');

    const utterance = new SpeechSynthesisUtterance(cleanSpeechText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Pick an English voice if available
    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(
      (v) => (v.lang.includes('en') || v.lang.includes('EN')) && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Medical'))
    ) || voices.find((v) => v.lang.includes('en'));

    if (naturalVoice) {
      utterance.voice = naturalVoice;
    }

    utterance.onend = () => {
      setIsSpeaking(false);
      setIsPaused(false);
    };

    utterance.onerror = () => {
      setIsSpeaking(false);
      setIsPaused(false);
    };

    window.speechSynthesis.speak(utterance);
    setIsSpeaking(true);
    setIsPaused(false);
  };

  const handleStopTTS = () => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      setIsPaused(false);
    }
  };

  return (
    <div className={`message-row ${isUser ? 'user-row' : 'assistant-row'}`}>
      <div className="message-avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="message-bubble-container">
        <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
          {isVoice && (
            <div className="voice-tag">
              <span>🎙️ Voice Message</span>
            </div>
          )}
          {message.audioUrl && (
            <div className="audio-player-wrapper">
              <audio controls src={message.audioUrl} preload="metadata" className="custom-audio-player">
                Your browser does not support the audio element.
              </audio>
            </div>
          )}
          
          {/* AI Voice Read-Aloud Toolbar */}
          {!isUser && (
            <div className="assistant-voice-toolbar">
              <button
                type="button"
                className={`btn-tts ${isSpeaking ? 'active-speaking' : ''}`}
                onClick={handlePlayTTS}
                title={isSpeaking ? (isPaused ? 'Resume AI Speech' : 'Pause AI Speech') : 'Listen to AI spoken answer'}
              >
                <span className="tts-icon">
                  {isSpeaking && !isPaused ? '⏸️' : '🔊'}
                </span>
                <span className="tts-label">
                  {isSpeaking ? (isPaused ? 'Resume Speech' : 'Playing Speech...') : 'Read Aloud'}
                </span>
              </button>

              {isSpeaking && (
                <button
                  type="button"
                  className="btn-tts-stop"
                  onClick={handleStopTTS}
                  title="Stop speech"
                >
                  ⏹️ Stop
                </button>
              )}
            </div>
          )}

          {isVoice ? (
            <div className="voice-transcript-block">
              <span className="transcript-label">Transcript:</span>
              <div className="transcript-text">{content}</div>
            </div>
          ) : (
            <div className="message-content">{content}</div>
          )}
          <div className="message-meta">
            <span className="message-time">{timestamp}</span>
          </div>
        </div>


        {/* Source Citations Section (Assistant Only) */}
        {!isUser && hasSources && (
          <div className="sources-container">
            <button
              className="sources-toggle-btn"
              onClick={() => setShowSources((prev) => !prev)}
              aria-expanded={showSources}
            >
              <span className="sources-toggle-icon">{showSources ? '▾' : '▸'}</span>
              <span>Grounded Citations ({ (patientSources?.length || 0) + (externalSources?.length || 0) } sources)</span>
            </button>

            {showSources && (
              <div className="sources-details">
                {patientSources && patientSources.length > 0 && (
                  <div className="source-group">
                    <span className="source-label">Patient EHR Record:</span>
                    <div className="source-chips">
                      {patientSources.map((src, i) => (
                        <span key={i} className="source-chip ehr-chip">
                          📄 {src}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {externalSources && externalSources.length > 0 && (
                  <div className="source-group">
                    <span className="source-label">External Medical Reference:</span>
                    <div className="source-chips">
                      {externalSources.map((src, i) => (
                        <span key={i} className="source-chip ext-chip">
                          📚 {src}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

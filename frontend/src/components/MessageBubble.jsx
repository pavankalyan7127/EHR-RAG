import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

const LANGUAGE_NAMES = {
  en: 'English',
  bn: 'বাংলা',
  gu: 'ગુજરાતી',
  hi: 'हिन्दी',
  mr: 'मराठी',
  pa: 'ਪੰਜਾਬੀ',
  ta: 'தமிழ்',
  te: 'తెలుగు',
  ur: 'اردو',
};

/**
 * MessageBubble Component
 * Renders user, assistant, or system error message bubbles.
 * Features collapsible source attribution tags for groundedness transparency,
 * neural TTS audio playback with browser speech fallback, and message-level language switching.
 */
export function MessageBubble({
  message,
  onSwitchLanguage = () => {},
  localizingMessageId = null,
}) {
  const [showSources, setShowSources] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const audioInstanceRef = useRef(null);

  const { role, content, timestamp, patientSources, externalSources } = message;
  const isVoice = message.isVoice || message.inputType === 'voice' || Boolean(message.audioUrl || message.audioFileId);
  const isLocalizing = localizingMessageId === message.id;

  // Helper to safely tear down an Audio instance and detach listeners
  const cleanupAudioInstance = () => {
    if (audioInstanceRef.current) {
      try {
        audioInstanceRef.current.pause();
        audioInstanceRef.current.onended = null;
        audioInstanceRef.current.onerror = null;
        audioInstanceRef.current.src = '';
      } catch (err) {
        console.warn('Audio cleanup warning:', err);
      }
      audioInstanceRef.current = null;
    }
    setIsPlayingAudio(false);
  };

  // Cleanup audio player and speech synthesis on unmount
  useEffect(() => {
    return () => {
      cleanupAudioInstance();
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        try {
          window.speechSynthesis.cancel();
        } catch (err) {
          console.warn('SpeechSynthesis cancel warning:', err);
        }
      }
    };
  }, []);

  // Stop previous neural audio if audioBase64 changes
  useEffect(() => {
    cleanupAudioInstance();
  }, [message.audioBase64]);

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

  // Neural TTS Audio Player for Backend-Generated Audio
  const handlePlayNeuralAudio = () => {
    if (!message.audioBase64) return;

    // Stop browser speech synthesis safely if active
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch (err) {
        console.warn('SpeechSynthesis cancel warning:', err);
      }
      setIsSpeaking(false);
      setIsPaused(false);
    }

    // Toggle pause/play if audio instance already exists
    if (audioInstanceRef.current) {
      if (isPlayingAudio) {
        try {
          audioInstanceRef.current.pause();
        } catch (err) {
          console.warn('Audio pause warning:', err);
        }
        setIsPlayingAudio(false);
      } else {
        try {
          const playPromise = audioInstanceRef.current.play();
          if (playPromise !== undefined && typeof playPromise.then === 'function') {
            playPromise
              .then(() => setIsPlayingAudio(true))
              .catch((err) => {
                console.error('Failed to resume audio:', err);
                setIsPlayingAudio(false);
              });
          } else {
            setIsPlayingAudio(true);
          }
        } catch (err) {
          console.error('Audio resume exception:', err);
          setIsPlayingAudio(false);
        }
      }
      return;
    }

    // Convert Base64 audio into a playable data URL using: data:${audioFormat || 'wav'};base64,${audioBase64}
    const rawFormat = message.audioFormat || 'wav';
    const audioFormat = rawFormat.includes('/') ? rawFormat : `audio/${rawFormat}`;
    const audioDataUrl = `data:${audioFormat || 'wav'};base64,${message.audioBase64}`;

    try {
      const audio = new Audio(audioDataUrl);
      audioInstanceRef.current = audio;

      audio.onended = () => {
        setIsPlayingAudio(false);
        audioInstanceRef.current = null;
      };

      audio.onerror = (err) => {
        console.error('Neural audio playback error:', err);
        cleanupAudioInstance();
      };

      const playPromise = audio.play();
      if (playPromise !== undefined && typeof playPromise.then === 'function') {
        playPromise
          .then(() => setIsPlayingAudio(true))
          .catch((err) => {
            console.error('Audio playback was prevented by browser:', err);
            cleanupAudioInstance();
          });
      } else {
        setIsPlayingAudio(true);
      }
    } catch (err) {
      console.error('Failed to initialize Audio element:', err);
      cleanupAudioInstance();
    }
  };

  const handleStopNeuralAudio = () => {
    cleanupAudioInstance();
  };

  // Text-to-Speech Controller for AI Assistant Answers (Fallback when audioBase64 is unavailable)
  const handlePlayTTS = () => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      alert('Text-to-speech is not supported in this browser.');
      return;
    }

    // Stop neural audio safely if playing
    cleanupAudioInstance();

    try {
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
      const cleanSpeechText = (content || '')
        .replace(/[*_#`~[\]]/g, '')
        .replace(/https?:\/\/\S+/g, 'link');

      const utterance = new SpeechSynthesisUtterance(cleanSpeechText);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      // Pick an English voice if available
      try {
        const voices = window.speechSynthesis.getVoices();
        const naturalVoice =
          voices.find(
            (v) =>
              (v.lang.includes('en') || v.lang.includes('EN')) &&
              (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Medical'))
          ) || voices.find((v) => v.lang.includes('en'));

        if (naturalVoice) {
          utterance.voice = naturalVoice;
        }
      } catch (voiceErr) {
        console.warn('Could not query speech synthesis voices:', voiceErr);
      }

      utterance.onend = () => {
        setIsSpeaking(false);
        setIsPaused(false);
      };

      utterance.onerror = (err) => {
        console.error('Speech synthesis utterance error:', err);
        setIsSpeaking(false);
        setIsPaused(false);
      };

      window.speechSynthesis.speak(utterance);
      setIsSpeaking(true);
      setIsPaused(false);
    } catch (err) {
      console.error('Speech synthesis failed:', err);
      setIsSpeaking(false);
      setIsPaused(false);
    }
  };

  const handleStopTTS = () => {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch (err) {
        console.warn('SpeechSynthesis cancel warning:', err);
      }
      setIsSpeaking(false);
      setIsPaused(false);
    }
  };

  const handleLanguageChange = (e) => {
    const newLang = e.target.value;
    if (newLang && newLang !== (message.language || 'en') && typeof onSwitchLanguage === 'function') {
      try {
        const result = onSwitchLanguage(message.id, newLang);
        if (result && typeof result.catch === 'function') {
          result.catch((err) => {
            console.error('onSwitchLanguage rejection caught:', err);
          });
        }
      } catch (err) {
        console.error('Error in onSwitchLanguage callback:', err);
      }
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
          
          {/* AI Voice & Localization Toolbar (Assistant Only) */}
          {!isUser && (
            <div className="assistant-voice-toolbar">
              {message.audioBase64 ? (
                <>
                  <button
                    type="button"
                    className={`btn-tts ${isPlayingAudio ? 'active-speaking' : ''}`}
                    onClick={handlePlayNeuralAudio}
                    title={isPlayingAudio ? 'Pause Audio' : 'Play neural TTS audio'}
                  >
                    <span className="tts-icon">
                      {isPlayingAudio ? '⏸️' : '🔊'}
                    </span>
                    <span className="tts-label">
                      {isPlayingAudio ? 'Playing Audio...' : 'Play Audio'}
                    </span>
                  </button>

                  {isPlayingAudio && (
                    <button
                      type="button"
                      className="btn-tts-stop"
                      onClick={handleStopNeuralAudio}
                      title="Stop audio"
                    >
                      ⏹️ Stop
                    </button>
                  )}
                </>
              ) : (
                <>
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
                </>
              )}

              {/* Message Language Badge & Selector */}
              <div
                className="message-language-controls"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  marginLeft: 'auto',
                }}
              >
                {message.language && (
                  <span
                    className="message-lang-badge"
                    style={{
                      fontSize: '0.74rem',
                      fontWeight: 600,
                      color: '#0369a1',
                      backgroundColor: '#f0f9ff',
                      padding: '2px 7px',
                      borderRadius: '4px',
                      border: '1px solid #e0f2fe',
                    }}
                    title={`Response language: ${LANGUAGE_NAMES[message.language] || message.language}`}
                  >
                    🌐 {LANGUAGE_NAMES[message.language] || message.language}
                  </span>
                )}

                {isLocalizing && (
                  <span
                    className="message-localizing-indicator"
                    style={{
                      fontSize: '0.74rem',
                      fontWeight: 600,
                      color: '#0284c7',
                    }}
                  >
                    ⏳ Translating...
                  </span>
                )}

                <select
                  className="message-lang-select"
                  value={message.language || 'en'}
                  disabled={isLocalizing}
                  onChange={handleLanguageChange}
                  aria-label="Switch response language"
                  title="Translate response language"
                  style={{
                    fontSize: '0.74rem',
                    fontWeight: 500,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: isLocalizing ? '#f1f5f9' : '#ffffff',
                    color: isLocalizing ? '#94a3b8' : '#334155',
                    cursor: isLocalizing ? 'not-allowed' : 'pointer',
                  }}
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
            </div>
          )}

          {isVoice ? (
            <div className="voice-transcript-block">
              <span className="transcript-label">Transcript:</span>
              {isUser ? (
                <div className="transcript-text">{content}</div>
              ) : (
                <div className="transcript-text markdown-body">
                  <ReactMarkdown>{content}</ReactMarkdown>
                </div>
              )}
            </div>
          ) : isUser ? (
            <div className="message-content">{content}</div>
          ) : (
            <div className="message-content markdown-body">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
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

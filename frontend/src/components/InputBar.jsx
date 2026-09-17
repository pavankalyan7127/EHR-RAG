import React, { useState, useRef } from 'react';

/**
 * InputBar Component
 * Provides text input, audio file upload, and live microphone recording (MediaRecorder API).
 */
export function InputBar({ onSendMessage, onSendVoiceMessage, isLoading, disabled }) {
  const [inputText, setInputText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  const fileInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerIntervalRef = useRef(null);

  const handleTextSubmit = (e) => {
    e?.preventDefault();
    if (!inputText.trim() || isLoading || disabled) return;
    onSendMessage(inputText);
    setInputText('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleTextSubmit();
    }
  };

  // 1. Audio File Picker Handler (Standard fallback)
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onSendVoiceMessage(file, file.name);
      e.target.value = ''; // Reset input
    }
  };

  const triggerFilePicker = () => {
    fileInputRef.current?.click();
  };

  // 2. Live Browser Microphone Recording Handler
  const startRecording = async () => {
    if (isRecording || isLoading || disabled) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Determine supported browser audio format
      let mimeType = 'audio/webm';
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        mimeType = 'audio/webm;codecs=opus';
      } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
        mimeType = 'audio/ogg;codecs=opus';
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        mimeType = 'audio/mp4';
      }

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        // Stop all tracks to release microphone hardware
        stream.getTracks().forEach((track) => track.stop());
        const ext = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('ogg') ? 'ogg' : 'webm';
        if (audioChunksRef.current.length > 0) {
          onSendVoiceMessage(audioBlob, `recorded_voice.${ext}`);
        }
      };

      // Request data in chunks every 250ms
      mediaRecorder.start(250);

      setIsRecording(true);
      setRecordingSeconds(0);

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.warn('Microphone access denied or unsupported, using file upload instead:', err);
      // Fallback to file picker if microphone is blocked
      triggerFilePicker();
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      // Force MediaRecorder to capture all buffered audio data before stopping
      try {
        if (mediaRecorderRef.current.state === 'recording') {
          mediaRecorderRef.current.requestData();
        }
      } catch (err) {
        console.warn('requestData error:', err);
      }
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    }
  };


  return (
    <footer className="input-bar-container">
      {/* Hidden file input for audio file picker */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="audio/*,.wav,.mp3,.m4a,.webm,.ogg"
        style={{ display: 'none' }}
      />

      <div className="input-bar">
        {isRecording ? (
          <div className="recording-active-bar">
            <div className="recording-status">
              <span className="recording-pulsing-dot"></span>
              <span className="recording-label">
                Recording Audio... ({recordingSeconds}s)
              </span>
            </div>
            <button
              type="button"
              className="btn-stop-recording"
              onClick={stopRecording}
              title="Stop recording and send query"
            >
              Done & Send ✈️
            </button>
          </div>
        ) : (
          <form className="input-form" onSubmit={handleTextSubmit}>
            <input
              type="text"
              className="chat-text-input"
              placeholder={
                disabled
                  ? 'Please select a patient first...'
                  : 'Ask a medical question about your EHR or condition...'
              }
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading || disabled}
              autoFocus
            />

            <div className="input-actions">
              {/* Voice / Mic Button */}
              <button
                type="button"
                className="action-btn mic-btn"
                onClick={startRecording}
                disabled={isLoading || disabled}
                title="Record voice query with microphone"
              >
                🎙️
              </button>

              {/* Upload Audio File Button */}
              <button
                type="button"
                className="action-btn upload-btn"
                onClick={triggerFilePicker}
                disabled={isLoading || disabled}
                title="Upload audio file (.wav, .mp3, .m4a)"
              >
                📁
              </button>

              {/* Send Button */}
              <button
                type="submit"
                className="btn-send"
                disabled={isLoading || disabled || !inputText.trim()}
                title="Send message"
              >
                <span>Send</span>
                <span className="send-arrow">➔</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </footer>
  );
}

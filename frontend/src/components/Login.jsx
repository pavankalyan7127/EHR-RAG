import React, { useState } from 'react';
import { login } from '../api/client';

export function Login({ onLoginSuccess }) {
  const [patientId, setPatientId] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!patientId.trim() || !password) return;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const data = await login({
        patientId: patientId.trim(),
        password: password,
      });
      if (onLoginSuccess) {
        onLoginSuccess(data.patient_id);
      }
    } catch (err) {
      console.error('Login error:', err);
      setErrorMessage(err.message || 'Invalid patient ID or password.');
    } finally {
      setIsLoading(false);
    }
  };

  const fillDemoCredentials = (demoId) => {
    setPatientId(demoId);
    setPassword(demoId);
    setErrorMessage(null);
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <div className="login-icon-badge">
            <span className="login-icon">🩺</span>
          </div>
          <h1>Medical NLP Assistant</h1>
          <p className="login-subtitle">Hospital Patient Portal</p>
        </div>

        {errorMessage && (
          <div className="login-alert-error" role="alert">
            <span className="alert-icon">⚠️</span>
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="patientId">Patient ID</label>
            <input
              id="patientId"
              type="text"
              placeholder="e.g. P017"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              required
              disabled={isLoading}
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              placeholder="Enter password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          <button
            type="submit"
            className="btn-login"
            disabled={isLoading || !patientId.trim() || !password}
          >
            {isLoading ? (
              <span className="login-spinner-wrapper">
                <span className="spinner-dot"></span> Authenticating...
              </span>
            ) : (
              'Sign In to Patient Portal'
            )}
          </button>
        </form>

        <div className="login-demo-box">
          <span className="demo-label">Demo Credentials:</span>
          <div className="demo-chips">
            <button
              type="button"
              className="demo-chip"
              onClick={() => fillDemoCredentials('P017')}
              title="Click to fill P017 credentials"
            >
              👤 Patient P017
            </button>
            <button
              type="button"
              className="demo-chip"
              onClick={() => fillDemoCredentials('P001')}
              title="Click to fill P001 credentials"
            >
              👤 Patient P001
            </button>
          </div>
          <p className="demo-note">Password equals Patient ID for demo hospital accounts.</p>
        </div>
      </div>
    </div>
  );
}

export default Login;

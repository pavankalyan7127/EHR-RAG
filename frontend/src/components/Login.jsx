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
        onLoginSuccess(data.patient_id, data.role || 'patient');
      }
    } catch (err) {
      console.error('Login error:', err);
      setErrorMessage(err.message || 'Invalid credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  const fillDemoCredentials = (demoId, demoPwd = null) => {
    setPatientId(demoId);
    setPassword(demoPwd || demoId);
    setErrorMessage(null);
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <div className="login-icon-badge">
            <span className="login-icon">🏥</span>
          </div>
          <h1>Medical NLP Assistant</h1>
          <p className="login-subtitle">Hospital Portal &amp; Admin System</p>
        </div>

        {errorMessage && (
          <div className="login-alert-error" role="alert">
            <span className="alert-icon">⚠️</span>
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="patientId">Patient ID / Username</label>
            <input
              id="patientId"
              type="text"
              placeholder="e.g. P017 or admin"
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
              'Sign In'
            )}
          </button>
        </form>

        <div className="login-demo-box">
          <span className="demo-label">Demo Credentials:</span>
          <div className="demo-chips">
            <button
              type="button"
              className="demo-chip demo-chip-admin"
              onClick={() => fillDemoCredentials('admin', 'Admin@123')}
              title="Click to fill Admin credentials"
            >
              👑 Administrator
            </button>
            <button
              type="button"
              className="demo-chip"
              onClick={() => fillDemoCredentials('P001')}
              title="Click to fill P001 credentials"
            >
              👤 Patient P001
            </button>
            <button
              type="button"
              className="demo-chip"
              onClick={() => fillDemoCredentials('P017')}
              title="Click to fill P017 credentials"
            >
              👤 Patient P017
            </button>
          </div>
          <p className="demo-note">Admin: admin / Admin@123 | Patients: P001 / P001</p>
        </div>
      </div>
    </div>
  );
}

export default Login;

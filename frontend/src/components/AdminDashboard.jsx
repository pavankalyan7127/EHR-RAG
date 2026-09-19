import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  getAdminPatients,
  createAdminPatient,
  updateAdminPatient,
  deleteAdminPatient,
  getAdminPatientRecords,
  createAdminRecord,
  updateAdminRecord,
  deleteAdminRecord,
} from '../api/client';

export function AdminDashboard({ onLogout }) {
  // State
  const [patients, setPatients] = useState([]);
  const [selectedPatientId, setSelectedPatientId] = useState(null);
  const [records, setRecords] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Loading & Alert States
  const [isLoadingPatients, setIsLoadingPatients] = useState(false);
  const [isLoadingRecords, setIsLoadingRecords] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Modals
  const [isAddPatientOpen, setIsAddPatientOpen] = useState(false);
  const [isEditPatientOpen, setIsEditPatientOpen] = useState(false);
  const [isAddRecordOpen, setIsAddRecordOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [confirmDeleteRecordId, setConfirmDeleteRecordId] = useState(null);
  const [confirmDeletePatient, setConfirmDeletePatient] = useState(false);

  // Form states
  const [patientForm, setPatientForm] = useState({
    patient_id: '',
    name: '',
    age: '',
    gender: 'Male',
    password: '',
  });

  const [editPatientForm, setEditPatientForm] = useState({
    name: '',
    age: '',
    gender: 'Male',
    is_active: true,
  });

  const [recordForm, setRecordForm] = useState({
    chunk_type: 'clinical_note',
    content: '',
    recorded_at: '',
  });

  const clearAlerts = () => {
    setStatusMessage(null);
    setErrorMessage(null);
  };

  // Load Patients
  const loadPatients = useCallback(async (selectIdAfter = null) => {
    setIsLoadingPatients(true);
    clearAlerts();
    try {
      const data = await getAdminPatients();
      setPatients(data);
      if (selectIdAfter) {
        setSelectedPatientId(selectIdAfter);
      } else if (!selectedPatientId && data.length > 0) {
        setSelectedPatientId(data[0].patient_id);
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load patients list.');
    } finally {
      setIsLoadingPatients(false);
    }
  }, [selectedPatientId]);

  useEffect(() => {
    loadPatients();
  }, [loadPatients]);

  // Load Records for selected patient
  const loadRecords = useCallback(async (patientId) => {
    if (!patientId) return;
    setIsLoadingRecords(true);
    try {
      const data = await getAdminPatientRecords(patientId);
      setRecords(data);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load medical records.');
    } finally {
      setIsLoadingRecords(false);
    }
  }, []);

  useEffect(() => {
    if (selectedPatientId) {
      loadRecords(selectedPatientId);
    } else {
      setRecords([]);
    }
  }, [selectedPatientId, loadRecords]);

  // Selected patient object
  const selectedPatient = useMemo(() => {
    return patients.find((p) => p.patient_id === selectedPatientId) || null;
  }, [patients, selectedPatientId]);

  // Filtered patients by search query
  const filteredPatients = useMemo(() => {
    if (!searchQuery.trim()) return patients;
    const q = searchQuery.toLowerCase().trim();
    return patients.filter(
      (p) =>
        p.patient_id.toLowerCase().includes(q) ||
        (p.name && p.name.toLowerCase().includes(q))
    );
  }, [patients, searchQuery]);

  // Format dates helper
  const formatDate = (dateStr) => {
    if (!dateStr) return 'Not recorded';
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short',
      });
    } catch {
      return dateStr;
    }
  };

  // ---------------------------------------------------------------------------
  // Patient Actions
  // ---------------------------------------------------------------------------

  const handleOpenAddPatient = () => {
    setPatientForm({
      patient_id: '',
      name: '',
      age: '',
      gender: 'Male',
      password: '',
    });
    setIsAddPatientOpen(true);
  };

  const handleCreatePatientSubmit = async (e) => {
    e.preventDefault();
    clearAlerts();
    try {
      const payload = {
        name: patientForm.name.trim(),
        age: patientForm.age ? parseInt(patientForm.age, 10) : null,
        gender: patientForm.gender,
      };
      if (patientForm.patient_id.trim()) {
        payload.patient_id = patientForm.patient_id.trim().toUpperCase();
      }
      if (patientForm.password.trim()) {
        payload.password = patientForm.password.trim();
      }

      const created = await createAdminPatient(payload);
      setStatusMessage(`Patient ${created.patient_id} created successfully.`);
      setIsAddPatientOpen(false);
      await loadPatients(created.patient_id);
    } catch (err) {
      setErrorMessage(err.message || 'Error creating patient.');
    }
  };

  const handleOpenEditPatient = () => {
    if (!selectedPatient) return;
    setEditPatientForm({
      name: selectedPatient.name || '',
      age: selectedPatient.age != null ? selectedPatient.age : '',
      gender: selectedPatient.gender || 'Male',
      is_active: selectedPatient.is_active,
    });
    setIsEditPatientOpen(true);
  };

  const handleUpdatePatientSubmit = async (e) => {
    e.preventDefault();
    clearAlerts();
    try {
      const payload = {
        name: editPatientForm.name.trim(),
        age: editPatientForm.age ? parseInt(editPatientForm.age, 10) : null,
        gender: editPatientForm.gender,
        is_active: editPatientForm.is_active,
      };
      const updated = await updateAdminPatient(selectedPatientId, payload);
      setStatusMessage(`Patient profile for ${updated.patient_id} updated.`);
      setIsEditPatientOpen(false);
      await loadPatients(selectedPatientId);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update patient.');
    }
  };

  // Toggle patient deactivation / reactivation (Normal workflow)
  const handleTogglePatientActive = async () => {
    if (!selectedPatient) return;
    clearAlerts();
    const newStatus = !selectedPatient.is_active;
    try {
      await updateAdminPatient(selectedPatientId, { is_active: newStatus });
      setStatusMessage(
        `Patient ${selectedPatientId} ${newStatus ? 'reactivated' : 'deactivated'} successfully.`
      );
      await loadPatients(selectedPatientId);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update patient active status.');
    }
  };

  // Permanent Delete Patient (Destructive operation with confirmation)
  const handlePermanentDeletePatient = async () => {
    if (!selectedPatientId) return;
    clearAlerts();
    try {
      await deleteAdminPatient(selectedPatientId);
      setStatusMessage(`Patient ${selectedPatientId} permanently deleted.`);
      setConfirmDeletePatient(false);
      setSelectedPatientId(null);
      await loadPatients();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to delete patient.');
    }
  };

  // ---------------------------------------------------------------------------
  // Medical Record Actions
  // ---------------------------------------------------------------------------

  const handleOpenAddRecord = () => {
    const nowLocal = new Date().toISOString().slice(0, 16);
    setRecordForm({
      chunk_type: 'clinical_note',
      content: '',
      recorded_at: nowLocal,
    });
    setIsAddRecordOpen(true);
  };

  const handleCreateRecordSubmit = async (e) => {
    e.preventDefault();
    clearAlerts();
    if (!recordForm.content.trim()) return;

    try {
      const payload = {
        chunk_type: recordForm.chunk_type,
        content: recordForm.content.trim(),
      };
      if (recordForm.recorded_at) {
        payload.recorded_at = new Date(recordForm.recorded_at).toISOString();
      }

      const created = await createAdminRecord(selectedPatientId, payload);
      setStatusMessage(`Medical record ${created._id} added successfully.`);
      setIsAddRecordOpen(false);
      await loadRecords(selectedPatientId);
      await loadPatients(selectedPatientId);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to add medical record.');
    }
  };

  const handleOpenEditRecord = (record) => {
    let recDate = '';
    if (record.recorded_at) {
      try {
        recDate = new Date(record.recorded_at).toISOString().slice(0, 16);
      } catch {
        recDate = '';
      }
    }
    setEditingRecord({
      ...record,
      recorded_at_input: recDate,
    });
  };

  const handleUpdateRecordSubmit = async (e) => {
    e.preventDefault();
    clearAlerts();
    if (!editingRecord || !editingRecord.content.trim()) return;

    try {
      const payload = {
        chunk_type: editingRecord.chunk_type,
        content: editingRecord.content.trim(),
      };
      if (editingRecord.recorded_at_input) {
        payload.recorded_at = new Date(editingRecord.recorded_at_input).toISOString();
      }

      await updateAdminRecord(selectedPatientId, editingRecord._id, payload);
      setStatusMessage(`Medical record ${editingRecord._id} updated.`);
      setEditingRecord(null);
      await loadRecords(selectedPatientId);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update record.');
    }
  };

  const handleDeleteRecord = async (recordId) => {
    clearAlerts();
    try {
      await deleteAdminRecord(selectedPatientId, recordId);
      setStatusMessage(`Medical record ${recordId} deleted.`);
      setConfirmDeleteRecordId(null);
      await loadRecords(selectedPatientId);
      await loadPatients(selectedPatientId);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to delete record.');
    }
  };

  return (
    <div className="admin-app">
      {/* Top Admin Header */}
      <header className="admin-header">
        <div className="admin-header-brand">
          <span className="admin-brand-icon">🏥</span>
          <div>
            <h1>Hospital EHR Administration</h1>
            <span className="admin-header-badge">Admin Dashboard &amp; Multi-Record Manager</span>
          </div>
        </div>

        <div className="admin-header-actions">
          <div className="admin-user-pill">
            <span className="pill-dot"></span>
            <span>Administrator (admin)</span>
          </div>
          <button
            type="button"
            className="btn-admin-refresh"
            onClick={() => loadPatients(selectedPatientId)}
            title="Refresh patient list"
          >
            🔄 Refresh
          </button>
          <button type="button" className="btn-admin-logout" onClick={onLogout}>
            Sign Out
          </button>
        </div>
      </header>

      {/* Global Alerts Banner */}
      {statusMessage && (
        <div className="admin-alert-banner success">
          <span>✅ {statusMessage}</span>
          <button type="button" onClick={() => setStatusMessage(null)}>✕</button>
        </div>
      )}
      {errorMessage && (
        <div className="admin-alert-banner error">
          <span>⚠️ {errorMessage}</span>
          <button type="button" onClick={() => setErrorMessage(null)}>✕</button>
        </div>
      )}

      {/* Main Split Layout */}
      <div className="admin-body">
        {/* Left Column: Patient Registry & Directory */}
        <aside className="admin-sidebar">
          <div className="sidebar-top-card">
            <div className="sidebar-title-row">
              <h2>Patients Directory</h2>
              <span className="count-chip">{patients.length}</span>
            </div>
            <button
              type="button"
              className="btn-add-patient"
              onClick={handleOpenAddPatient}
            >
              + Add Patient
            </button>
          </div>

          <div className="sidebar-search">
            <input
              type="text"
              placeholder="Search by ID or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="patient-list">
            {isLoadingPatients ? (
              <div className="admin-loading-state">Loading patient registry...</div>
            ) : filteredPatients.length === 0 ? (
              <div className="admin-empty-state">No matching patients found.</div>
            ) : (
              filteredPatients.map((p) => {
                const isSelected = p.patient_id === selectedPatientId;
                return (
                  <div
                    key={p.patient_id}
                    className={`patient-card-item ${isSelected ? 'active' : ''} ${
                      !p.is_active ? 'deactivated' : ''
                    }`}
                    onClick={() => setSelectedPatientId(p.patient_id)}
                  >
                    <div className="card-item-header">
                      <span className="patient-id-badge">{p.patient_id}</span>
                      <span
                        className={`status-dot-badge ${
                          p.is_active ? 'active' : 'inactive'
                        }`}
                      >
                        {p.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </div>

                    <div className="card-patient-name">{p.name || `Patient ${p.patient_id}`}</div>

                    <div className="card-item-footer">
                      <span className="card-meta">
                        {p.age ? `${p.age} yrs` : 'Age N/A'} • {p.gender || 'N/A'}
                      </span>
                      <span className="record-count-chip">
                        {p.record_count} {p.record_count === 1 ? 'Record' : 'Records'}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Column: Selected Patient Details & EHR Records */}
        <main className="admin-content-area">
          {!selectedPatient ? (
            <div className="admin-welcome-placeholder">
              <div className="placeholder-content">
                <span className="placeholder-icon">📋</span>
                <h3>No Patient Selected</h3>
                <p>Select a patient from the directory on the left or add a new patient to view and manage their medical records.</p>
              </div>
            </div>
          ) : (
            <div className="patient-management-view">
              {/* Patient Profile Card */}
              <div className="patient-profile-card">
                <div className="profile-info-block">
                  <div className="profile-title-line">
                    <h2>{selectedPatient.name || `Patient ${selectedPatient.patient_id}`}</h2>
                    <span className="patient-id-pill">{selectedPatient.patient_id}</span>
                    <span
                      className={`status-pill ${
                        selectedPatient.is_active ? 'status-active' : 'status-deactivated'
                      }`}
                    >
                      {selectedPatient.is_active ? 'Active' : 'Deactivated'}
                    </span>
                  </div>

                  <div className="profile-demographics-row">
                    <div className="demographic-item">
                      <span className="label">Age</span>
                      <span className="value">{selectedPatient.age ? `${selectedPatient.age} years` : 'Not specified'}</span>
                    </div>
                    <div className="demographic-item">
                      <span className="label">Gender</span>
                      <span className="value">{selectedPatient.gender || 'Not specified'}</span>
                    </div>
                    <div className="demographic-item">
                      <span className="label">EHR Records</span>
                      <span className="value font-semibold">{records.length}</span>
                    </div>
                    <div className="demographic-item">
                      <span className="label">Registered</span>
                      <span className="value">{formatDate(selectedPatient.created_at)}</span>
                    </div>
                  </div>
                </div>

                {/* Patient Control Actions */}
                <div className="profile-actions-block">
                  <button
                    type="button"
                    className="btn-action btn-edit-profile"
                    onClick={handleOpenEditPatient}
                  >
                    ✏️ Edit Patient
                  </button>

                  <button
                    type="button"
                    className={`btn-action ${
                      selectedPatient.is_active ? 'btn-deactivate' : 'btn-reactivate'
                    }`}
                    onClick={handleTogglePatientActive}
                    title={
                      selectedPatient.is_active
                        ? 'Deactivate patient login (preserves all records)'
                        : 'Reactivate patient account'
                    }
                  >
                    {selectedPatient.is_active ? '🚫 Deactivate' : '✅ Reactivate'}
                  </button>

                  <button
                    type="button"
                    className="btn-action btn-danger-delete"
                    onClick={() => setConfirmDeletePatient(true)}
                    title="Permanently delete patient and all records"
                  >
                    🗑️ Delete Patient
                  </button>
                </div>
              </div>

              {/* Medical Records Section */}
              <div className="patient-records-section">
                <div className="records-header-row">
                  <div className="records-title-group">
                    <h3>Patient Clinical &amp; Medical Records</h3>
                    <span className="records-counter-tag">
                      {records.length} {records.length === 1 ? 'Record' : 'Records'} Available
                    </span>
                  </div>

                  <button
                    type="button"
                    className="btn-add-record"
                    onClick={handleOpenAddRecord}
                  >
                    + Add Medical Record
                  </button>
                </div>

                {isLoadingRecords ? (
                  <div className="records-loading-card">Loading medical record history...</div>
                ) : records.length === 0 ? (
                  <div className="records-empty-card">
                    <span className="empty-icon">📂</span>
                    <h4>No Medical Records on File</h4>
                    <p>This patient currently has zero clinical notes recorded. Click "+ Add Medical Record" above to document a consultation.</p>
                  </div>
                ) : (
                  <div className="records-timeline">
                    {records.map((rec) => (
                      <div key={rec._id} className="record-card">
                        <div className="record-card-top">
                          <div className="record-meta-tags">
                            <span className="chunk-type-badge">{rec.chunk_type || 'clinical_note'}</span>
                            <span className="record-id-chip">{rec._id}</span>
                            <span className="recorded-date">
                              📅 Consultation: {formatDate(rec.recorded_at)}
                            </span>
                          </div>

                          <div className="record-card-actions">
                            <button
                              type="button"
                              className="btn-rec-edit"
                              onClick={() => handleOpenEditRecord(rec)}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn-rec-delete"
                              onClick={() => setConfirmDeleteRecordId(rec._id)}
                            >
                              Delete
                            </button>
                          </div>
                        </div>

                        <div className="record-content-box">
                          <p>{rec.content}</p>
                        </div>

                        <div className="record-card-timestamps">
                          <span>Entered: {formatDate(rec.created_at)}</span>
                          {rec.updated_at && (
                            <span>Modified: {formatDate(rec.updated_at)}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ========================================================================= */}
      {/* MODALS */}
      {/* ========================================================================= */}

      {/* 1. Add Patient Modal */}
      {isAddPatientOpen && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card">
            <div className="modal-header">
              <h3>Register New Patient</h3>
              <button type="button" onClick={() => setIsAddPatientOpen(false)}>✕</button>
            </div>

            <form onSubmit={handleCreatePatientSubmit} className="modal-form">
              <div className="form-group">
                <label>Patient ID (Optional)</label>
                <input
                  type="text"
                  placeholder="Leave empty for auto-generated ID (e.g. P031)"
                  value={patientForm.patient_id}
                  onChange={(e) =>
                    setPatientForm({ ...patientForm, patient_id: e.target.value })
                  }
                />
                <small className="form-helper-text">
                  The system will safely generate the next available sequential ID if blank.
                </small>
              </div>

              <div className="form-group">
                <label>Full Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Eleanor Vance"
                  value={patientForm.name}
                  onChange={(e) =>
                    setPatientForm({ ...patientForm, name: e.target.value })
                  }
                />
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label>Age</label>
                  <input
                    type="number"
                    min="0"
                    max="125"
                    placeholder="e.g. 58"
                    value={patientForm.age}
                    onChange={(e) =>
                      setPatientForm({ ...patientForm, age: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label>Gender</label>
                  <select
                    value={patientForm.gender}
                    onChange={(e) =>
                      setPatientForm({ ...patientForm, gender: e.target.value })
                    }
                  >
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Account Password (Optional)</label>
                <input
                  type="password"
                  placeholder="Defaults to Patient ID if omitted"
                  value={patientForm.password}
                  onChange={(e) =>
                    setPatientForm({ ...patientForm, password: e.target.value })
                  }
                />
              </div>

              <div className="modal-buttons">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setIsAddPatientOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm">
                  Create Patient Account
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 2. Edit Patient Modal */}
      {isEditPatientOpen && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card">
            <div className="modal-header">
              <h3>Edit Patient Profile ({selectedPatientId})</h3>
              <button type="button" onClick={() => setIsEditPatientOpen(false)}>✕</button>
            </div>

            <form onSubmit={handleUpdatePatientSubmit} className="modal-form">
              <div className="form-group">
                <label>Full Name</label>
                <input
                  type="text"
                  required
                  value={editPatientForm.name}
                  onChange={(e) =>
                    setEditPatientForm({ ...editPatientForm, name: e.target.value })
                  }
                />
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label>Age</label>
                  <input
                    type="number"
                    min="0"
                    max="125"
                    value={editPatientForm.age}
                    onChange={(e) =>
                      setEditPatientForm({ ...editPatientForm, age: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label>Gender</label>
                  <select
                    value={editPatientForm.gender}
                    onChange={(e) =>
                      setEditPatientForm({ ...editPatientForm, gender: e.target.value })
                    }
                  >
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={editPatientForm.is_active}
                    onChange={(e) =>
                      setEditPatientForm({
                        ...editPatientForm,
                        is_active: e.target.checked,
                      })
                    }
                  />
                  <span>Account Active (Uncheck to deactivate patient login access)</span>
                </label>
              </div>

              <div className="modal-buttons">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setIsEditPatientOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm">
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 3. Add Medical Record Modal */}
      {isAddRecordOpen && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card large-modal">
            <div className="modal-header">
              <h3>Add Medical Record for Patient {selectedPatientId}</h3>
              <button type="button" onClick={() => setIsAddRecordOpen(false)}>✕</button>
            </div>

            <form onSubmit={handleCreateRecordSubmit} className="modal-form">
              <div className="form-row-2">
                <div className="form-group">
                  <label>Record Type</label>
                  <select
                    value={recordForm.chunk_type}
                    onChange={(e) =>
                      setRecordForm({ ...recordForm, chunk_type: e.target.value })
                    }
                  >
                    <option value="clinical_note">Clinical Note</option>
                    <option value="initial_consultation">Initial Consultation</option>
                    <option value="follow_up">Follow-Up Note</option>
                    <option value="medication">Medication &amp; Prescription</option>
                    <option value="lab_result">Laboratory / Diagnostic Result</option>
                    <option value="specialist_note">Specialist Consultation</option>
                    <option value="discharge_summary">Discharge Summary</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Consultation Date / Time</label>
                  <input
                    type="datetime-local"
                    value={recordForm.recorded_at}
                    onChange={(e) =>
                      setRecordForm({ ...recordForm, recorded_at: e.target.value })
                    }
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Medical Note Content *</label>
                <textarea
                  rows="6"
                  required
                  placeholder="Document patient clinical findings, vitals, assessment, and treatment plan..."
                  value={recordForm.content}
                  onChange={(e) =>
                    setRecordForm({ ...recordForm, content: e.target.value })
                  }
                />
              </div>

              <div className="modal-info-note">
                ℹ️ The backend will automatically generate the next non-reusable sequence record ID (e.g. ehr_{selectedPatientId}_00X). The new record is immediately available to the RAG assistant.
              </div>

              <div className="modal-buttons">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setIsAddRecordOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm">
                  Save Medical Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 4. Edit Medical Record Modal */}
      {editingRecord && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card large-modal">
            <div className="modal-header">
              <h3>Edit Record: {editingRecord._id}</h3>
              <button type="button" onClick={() => setEditingRecord(null)}>✕</button>
            </div>

            <form onSubmit={handleUpdateRecordSubmit} className="modal-form">
              <div className="form-row-2">
                <div className="form-group">
                  <label>Record Type</label>
                  <select
                    value={editingRecord.chunk_type}
                    onChange={(e) =>
                      setEditingRecord({ ...editingRecord, chunk_type: e.target.value })
                    }
                  >
                    <option value="clinical_note">Clinical Note</option>
                    <option value="initial_consultation">Initial Consultation</option>
                    <option value="follow_up">Follow-Up Note</option>
                    <option value="medication">Medication &amp; Prescription</option>
                    <option value="lab_result">Laboratory / Diagnostic Result</option>
                    <option value="specialist_note">Specialist Consultation</option>
                    <option value="discharge_summary">Discharge Summary</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Consultation Date / Time</label>
                  <input
                    type="datetime-local"
                    value={editingRecord.recorded_at_input}
                    onChange={(e) =>
                      setEditingRecord({
                        ...editingRecord,
                        recorded_at_input: e.target.value,
                      })
                    }
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Medical Note Content *</label>
                <textarea
                  rows="6"
                  required
                  value={editingRecord.content}
                  onChange={(e) =>
                    setEditingRecord({ ...editingRecord, content: e.target.value })
                  }
                />
              </div>

              <div className="modal-buttons">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setEditingRecord(null)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm">
                  Update Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 5. Delete Record Confirmation Modal */}
      {confirmDeleteRecordId && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card confirmation-modal">
            <div className="modal-header">
              <h3>Confirm Medical Record Deletion</h3>
              <button type="button" onClick={() => setConfirmDeleteRecordId(null)}>✕</button>
            </div>
            <p className="confirm-text">
              Are you sure you want to delete medical record <strong>{confirmDeleteRecordId}</strong>?
            </p>
            <p className="confirm-subtext">
              Note: This document will be permanently removed. To maintain clinical history integrity, its sequence number will <strong>never be reused</strong> for future records.
            </p>
            <div className="modal-buttons">
              <button
                type="button"
                className="btn-cancel"
                onClick={() => setConfirmDeleteRecordId(null)}
              >
                Keep Record
              </button>
              <button
                type="button"
                className="btn-danger-confirm"
                onClick={() => handleDeleteRecord(confirmDeleteRecordId)}
              >
                Delete Record
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. Delete Patient Permanent Confirmation Modal */}
      {confirmDeletePatient && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card confirmation-modal">
            <div className="modal-header">
              <h3>Permanently Delete Patient?</h3>
              <button type="button" onClick={() => setConfirmDeletePatient(false)}>✕</button>
            </div>
            <p className="confirm-text">
              Are you sure you want to permanently delete patient <strong>{selectedPatientId}</strong>?
            </p>
            <div className="modal-warning-box">
              ⚠️ <strong>Destructive Operation:</strong> This will erase all demographic records, {records.length} EHR clinical documents, chat sessions, message history, and voice recordings.
              <br /><br />
              💡 <em>Tip: To temporarily block login access while preserving all clinical data, use the <strong>Deactivate</strong> button instead.</em>
            </div>
            <div className="modal-buttons">
              <button
                type="button"
                className="btn-cancel"
                onClick={() => setConfirmDeletePatient(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-danger-confirm"
                onClick={handlePermanentDeletePatient}
              >
                Permanently Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminDashboard;

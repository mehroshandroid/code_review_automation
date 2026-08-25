import { useState } from "react";

export default function ProjectDialog({ title, initialName, submitLabel, onSubmit, onClose }) {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      await onSubmit(name.trim());
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">{title}</div>
        <div className="dialog-body">
          <div className="field">
            <label htmlFor="projectDialogName">Project name</label>
            <input
              id="projectDialogName"
              type="text"
              className="input"
              value={name}
              autoFocus
              disabled={saving}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
            {saving ? "Saving…" : submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

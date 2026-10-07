import { useState } from "react";
import { PLATFORMS } from "../platforms";

const PLATFORM_LABELS = PLATFORMS.filter((p) => p.available).map((p) => p.label);

export default function ProjectDialog({ title, initialName, submitLabel, onSubmit, onClose, initialPlatforms = [], withPlatforms = false }) {
  const [name, setName] = useState(initialName);
  const [platforms, setPlatforms] = useState(initialPlatforms);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      if (withPlatforms) {
        await onSubmit(name.trim(), PLATFORM_LABELS.filter((p) => platforms.includes(p)));
      } else {
        await onSubmit(name.trim());
      }
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
          {withPlatforms && (
            <fieldset className="field" style={{ border: "none", padding: 0, margin: "var(--space-3) 0 0" }}>
              <legend style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Platforms</legend>
              <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
                {PLATFORM_LABELS.map((platform) => (
                  <label key={platform} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
                    <input
                      type="checkbox" checked={platforms.includes(platform)} disabled={saving}
                      onChange={() => setPlatforms((current) => (current.includes(platform) ? current.filter((p) => p !== platform) : [...current, platform]))}
                    />
                    {platform}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
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

import { useEffect, useState } from "react";
import { getReviewers, initiateCycle } from "../services/api";

export default function InitiateCycleDialog({ project, year, entry, onInitiated, onClose }) {
  const [reviewers, setReviewers] = useState([]);
  const [selected, setSelected] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getReviewers().then((result) => { if (!cancelled) setReviewers(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const complete = project.platforms.every((platform) => selected[platform]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await initiateCycle(project.id, {
        year, quarter: entry.quarter,
        assignments: project.platforms.map((platform) => ({ platform, reviewer_id: selected[platform] })),
      });
      onInitiated(updated);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate the review.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Initiate Q{entry.quarter} {year} review — {project.name}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <p className="card-body" style={{ margin: 0 }}>Assign a reviewer to each platform.</p>
          {project.platforms.map((platform) => (
            <div className="field" key={platform}>
              <label htmlFor={`reviewer-${platform}`}>{platform}</label>
              <select
                id={`reviewer-${platform}`} aria-label={`Reviewer for ${platform}`} className="input"
                value={selected[platform] || ""}
                onChange={(event) => setSelected((current) => ({ ...current, [platform]: event.target.value }))}
              >
                <option value="" disabled>Choose a reviewer…</option>
                {reviewers.map((reviewer) => (
                  <option key={reviewer.id} value={reviewer.id}>{reviewer.name || reviewer.email}</option>
                ))}
              </select>
            </div>
          ))}
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || !complete}>{saving ? "Initiating…" : "Initiate"}</button>
        </div>
      </form>
    </div>
  );
}

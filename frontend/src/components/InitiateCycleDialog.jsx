import { useEffect, useState } from "react";
import { getReviewers, initiateCycle } from "../services/api";

export default function InitiateCycleDialog({ project, year, entry, onInitiated, onClose }) {
  const [reviewers, setReviewers] = useState([]);
  const [selected, setSelected] = useState({});
  // Adding to a quarter that's already started offers only the platforms not started yet.
  const adding = Boolean(entry.cycle);
  const offered = adding ? (entry.uninitiated_platforms || []) : project.platforms;
  const [ticked, setTicked] = useState(() => Object.fromEntries(offered.map((platform) => [platform, true])));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getReviewers().then((result) => { if (!cancelled) setReviewers(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const chosen = offered.filter((platform) => ticked[platform]);
  const complete = chosen.length > 0 && chosen.every((platform) => selected[platform]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await initiateCycle(project.id, {
        year, quarter: entry.quarter,
        assignments: chosen.map((platform) => ({ platform, reviewer_id: selected[platform] })),
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
        <div className="dialog-title">
          {adding ? `Add platforms — ${project.name} · Q${entry.quarter} ${year}` : `Initiate Q${entry.quarter} ${year} review — ${project.name}`}
        </div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <p className="card-body" style={{ margin: 0 }}>
            Tick the platforms to start now and assign each a reviewer. The rest can be started later.
          </p>
          {offered.map((platform) => (
            <div className="field" key={platform}>
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox" aria-label={`Start ${platform}`} checked={!!ticked[platform]}
                  onChange={(event) => setTicked((current) => ({ ...current, [platform]: event.target.checked }))}
                />
                {platform}
              </label>
              {ticked[platform] && (
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
              )}
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

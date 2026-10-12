import { useEffect, useState } from "react";
import { bulkInitiate, getBulkPreview, getReviewers } from "../services/api";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function BulkInitiateDialog({ year, quarters, onDone, onClose }) {
  const [quarter, setQuarter] = useState(quarters[quarters.length - 1]);
  const [reviewers, setReviewers] = useState([]);
  const [preview, setPreview] = useState(null);
  const [included, setIncluded] = useState({}); // project_id -> bool
  const [selected, setSelected] = useState({}); // project_id -> { platform: reviewer_id }
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getReviewers().then((result) => { if (!cancelled) setReviewers(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setLoadError("");
    getBulkPreview(year, quarter)
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setIncluded(Object.fromEntries(result.eligible.map((p) => [p.project_id, true])));
        setSelected(Object.fromEntries(result.eligible.map((p) => [
          p.project_id, Object.fromEntries(p.platforms.map((platform) => [platform, p.suggested_reviewers[platform] || ""])),
        ])));
      })
      .catch(() => { if (!cancelled) setLoadError("Couldn't load the projects for this quarter."); });
    return () => { cancelled = true; };
  }, [year, quarter]);

  const eligible = preview?.eligible || [];
  const ticked = eligible.filter((p) => included[p.project_id]);
  const complete = ticked.length > 0 && ticked.every((p) => p.platforms.every((platform) => selected[p.project_id]?.[platform]));
  const allPlatforms = [...new Set(eligible.flatMap((p) => p.platforms))];

  function choose(projectId, platform, reviewerId) {
    setSelected((current) => ({ ...current, [projectId]: { ...current[projectId], [platform]: reviewerId } }));
  }

  function setForAll(platform, reviewerId) {
    if (!reviewerId) return;
    // Only fills empty slots: a pre-filled or hand-picked reviewer is never overwritten.
    setSelected((current) => Object.fromEntries(Object.entries(current).map(([projectId, slots]) => [
      projectId, platform in slots && !slots[platform] ? { ...slots, [platform]: reviewerId } : slots,
    ])));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await bulkInitiate({
        year, quarter,
        projects: ticked.map((p) => ({
          project_id: p.project_id,
          assignments: p.platforms.map((platform) => ({ platform, reviewer_id: selected[p.project_id][platform] })),
        })),
      });
      setResults(response.results);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate the reviews.");
    } finally {
      setSaving(false);
    }
  }

  const reviewerOptions = reviewers.map((reviewer) => (
    <option key={reviewer.id} value={reviewer.id}>{reviewer.name || reviewer.email}</option>
  ));

  if (results) {
    const started = results.filter((r) => r.status === "started");
    const skipped = results.filter((r) => r.status !== "started");
    return (
      <div className="dialog-backdrop">
        <div className="dialog" style={{ maxWidth: 640 }}>
          <div className="dialog-title">Q{quarter} {year} reviews</div>
          <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
            <p className="card-body" style={{ margin: 0 }}>Started {started.length} of {plural(results.length, "project")}.</p>
            {started.length > 0 && (
              <p className="card-body" style={{ margin: 0 }}>Each PM and reviewer gets one email listing their projects.</p>
            )}
            {skipped.length > 0 && (
              <ul className="card-body" style={{ margin: 0, paddingLeft: 18 }}>
                {skipped.map((r) => <li key={r.project_id}>{r.project_name || r.project_id}: {r.reason}</li>)}
              </ul>
            )}
          </div>
          <div className="dialog-actions">
            <button type="button" className="btn btn-primary" onClick={() => { onDone(); onClose(); }}>Done</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" style={{ maxWidth: 900, width: "100%" }} onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Initiate a quarter for all projects</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)", maxHeight: "70vh", overflowY: "auto" }}>
          <div className="field" style={{ maxWidth: 200 }}>
            <label htmlFor="bulk-quarter">Quarter</label>
            <select id="bulk-quarter" className="input" value={quarter} onChange={(event) => setQuarter(Number(event.target.value))}>
              {[...quarters].sort((a, b) => b - a).map((q) => <option key={q} value={q}>Q{q} {year}</option>)}
            </select>
          </div>

          {loadError && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{loadError}</p>}
          {!preview && !loadError && <p className="card-body" style={{ margin: 0 }}>Loading projects…</p>}

          {preview && eligible.length === 0 && (
            <p className="card-body" style={{ margin: 0 }}>No projects can be initiated for this quarter.</p>
          )}

          {eligible.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="table table--padded">
                <thead>
                  <tr>
                    <th aria-label="Include" />
                    <th>Project</th>
                    <th>PMs</th>
                    {allPlatforms.map((platform) => (
                      <th key={platform}>
                        <div style={{ display: "grid", gap: 4 }}>
                          <span>{platform}</span>
                          <select
                            aria-label={`Set all ${platform} reviewers`} className="input" value=""
                            onChange={(event) => setForAll(platform, event.target.value)}
                          >
                            <option value="">Set for all…</option>
                            {reviewerOptions}
                          </select>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {eligible.map((p) => (
                    <tr key={p.project_id} aria-label={p.project_name}>
                      <td>
                        <input
                          type="checkbox" aria-label={`Include ${p.project_name}`} checked={!!included[p.project_id]}
                          onChange={(event) => setIncluded((current) => ({ ...current, [p.project_id]: event.target.checked }))}
                        />
                      </td>
                      <td>{p.project_name}</td>
                      <td>
                        {p.managers.length === 0 ? (
                          <span style={{ color: "var(--color-brand-coral)" }}>No PM assigned — nobody will be emailed</span>
                        ) : (
                          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                            {p.managers.map((m) => <span key={m.id} className="tag tag-outline">{m.name}</span>)}
                          </div>
                        )}
                      </td>
                      {allPlatforms.map((platform) => (
                        <td key={platform}>
                          {p.platforms.includes(platform) ? (
                            <select
                              aria-label={`${p.project_name} reviewer for ${platform}`} className="input"
                              value={selected[p.project_id]?.[platform] || ""} disabled={!included[p.project_id]}
                              onChange={(event) => choose(p.project_id, platform, event.target.value)}
                            >
                              <option value="" disabled>Choose…</option>
                              {reviewerOptions}
                            </select>
                          ) : <span className="card-body">—</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {preview && preview.skipped.length > 0 && (
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Not included</div>
              <ul className="card-body" style={{ margin: 0, paddingLeft: 18 }}>
                {preview.skipped.map((s) => (
                  <li key={s.project_id}><span>{s.project_name}</span> — <span>{s.reason}</span></li>
                ))}
              </ul>
            </div>
          )}

          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || !complete}>
            {saving ? "Initiating…" : `Initiate ${plural(ticked.length, "project")}`}
          </button>
        </div>
      </form>
    </div>
  );
}

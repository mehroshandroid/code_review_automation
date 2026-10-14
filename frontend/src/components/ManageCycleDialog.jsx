import { useEffect, useState } from "react";
import AssignmentStatusBadge from "./AssignmentStatusBadge";
import { relativeTime, StageTimeline } from "./StageTracker";
import { Link } from "react-router-dom";
import {
  changeAssignmentReviewer, getReviewers, reinitiateAssignment, remindAssignment, rerunAssignment, rerunAssignmentZip, retryAssignment,
} from "../services/api";

function shortDate(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—";
}

export default function ManageCycleDialog({ project, year, entry, onChanged, onClose, onAddPlatforms }) {
  const cycleId = entry.cycle.id;
  const [assignments, setAssignments] = useState(entry.cycle.assignments);
  const [reviewers, setReviewers] = useState([]);
  const [error, setError] = useState("");
  const [rerunFor, setRerunFor] = useState(null);
  const [rerunUrl, setRerunUrl] = useState("");
  const [rerunBranch, setRerunBranch] = useState("");
  const [rerunMode, setRerunMode] = useState("url");
  const [rerunZip, setRerunZip] = useState(null);
  const [reinitFor, setReinitFor] = useState(null); // { platform, round }
  const [reinitReviewer, setReinitReviewer] = useState("");
  const [historyOpen, setHistoryOpen] = useState({});
  const notStarted = entry.uninitiated_platforms || [];

  useEffect(() => {
    let cancelled = false;
    getReviewers().then((result) => { if (!cancelled) setReviewers(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  async function act(request) {
    setError("");
    try {
      const updated = await request();
      setAssignments((current) => current.map((a) => (a.platform === updated.platform ? updated : a)));
      onChanged();
      return true;
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong.");
      return false;
    }
  }

  function reviewerOptions(assignment) {
    const known = reviewers.some((r) => r.id === assignment.reviewer_id);
    const extra = assignment.reviewer_id && !known ? [{ id: assignment.reviewer_id, name: assignment.reviewer_name || assignment.reviewer_id }] : [];
    return [...reviewers, ...extra];
  }

  async function handleRerun(event) {
    event.preventDefault();
    const request = rerunMode === "zip"
      ? () => rerunAssignmentZip(cycleId, rerunFor, rerunZip)
      : () => rerunAssignment(cycleId, rerunFor, { devopsUrl: rerunUrl.trim(), devopsBranch: rerunBranch.trim() });
    if (await act(request)) {
      setRerunFor(null);
    }
  }

  async function handleReinitiate(event) {
    event.preventDefault();
    if (await act(() => reinitiateAssignment(cycleId, reinitFor.platform, reinitReviewer))) {
      setReinitFor(null);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label="Manage review cycle" style={{ maxWidth: 760 }} onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">Q{entry.quarter} {year} review — {project.name}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="table table--padded">
              <thead><tr><th>Platform</th><th>Status</th><th>Progress</th><th>Reviewer</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {assignments.map((assignment) => {
                  const approved = assignment.review_status === "approved";
                  return (
                    <tr key={assignment.platform}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{assignment.platform}</div>
                        {assignment.round > 1 && <div className="quarter-card-meta">Round {assignment.round}</div>}
                        <div className="quarter-card-meta" style={{ wordBreak: "break-all" }}>
                          {assignment.source_type === "zip" ? `Zip: ${assignment.source_zip_name}` : assignment.devops_url || "No source yet"}
                        </div>
                      </td>
                      <td>
                        <AssignmentStatusBadge assignment={assignment} />
                        {assignment.run_status === "failed" && assignment.run_error && <div className="run-error">{assignment.run_error}</div>}
                      </td>
                      <td><StageTimeline assignment={assignment} initiatedAt={entry.cycle.initiated_at} /></td>
                      <td>
                        <select
                          aria-label={`Reviewer for ${assignment.platform}`} className="input" disabled={approved}
                          value={assignment.reviewer_id || ""}
                          onChange={(event) => act(() => changeAssignmentReviewer(cycleId, assignment.platform, event.target.value))}
                        >
                          {!assignment.reviewer_id && <option value="" disabled>Choose…</option>}
                          {reviewerOptions(assignment).map((reviewer) => (
                            <option key={reviewer.id} value={reviewer.id}>{reviewer.name || reviewer.email}</option>
                          ))}
                        </select>
                      </td>
                      <td style={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
                        {(assignment.run_status === "waiting_for_url" || (assignment.run_status === "failed" && assignment.failure_kind === "url")) && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => remindAssignment(cycleId, assignment.platform, "pm"))}>Remind PM</button>
                        )}
                        {assignment.run_status === "completed" && !approved && assignment.reviewer_id && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => remindAssignment(cycleId, assignment.platform, "reviewer"))}>Remind reviewer</button>
                        )}
                        {assignment.run_status === "failed" && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => retryAssignment(cycleId, assignment.platform))}>Retry</button>
                        )}
                        {assignment.run_status === "completed" && !approved && (
                          <button type="button" className="btn btn-ghost" onClick={() => {
                            setRerunFor(assignment.platform);
                            setRerunUrl(assignment.devops_url || "");
                            setRerunBranch(assignment.devops_branch || "");
                            setRerunMode(assignment.source_type === "zip" ? "zip" : "url");
                            setRerunZip(null);
                          }}>Re-run</button>
                        )}
                        {assignment.can_reinitiate && (
                          <button type="button" className="btn btn-ghost" onClick={() => {
                            setReinitFor({ platform: assignment.platform, round: (assignment.round || 1) + 1 });
                            setReinitReviewer(assignment.reviewer_id || "");
                          }}>Reinitiate</button>
                        )}
                        {assignment.history?.length > 0 && (
                          <div>
                            <button
                              type="button" className="btn btn-ghost" aria-expanded={!!historyOpen[assignment.platform]}
                              onClick={() => setHistoryOpen((current) => ({ ...current, [assignment.platform]: !current[assignment.platform] }))}
                            >Earlier rounds ({assignment.history.length})</button>
                            {historyOpen[assignment.platform] && (
                              <ul className="quarter-card-meta" style={{ margin: 0, paddingLeft: 16 }}>
                                {assignment.history.map((past) => (
                                  <li key={past.round}>
                                    {past.review_id ? <Link to={`/reports/${past.review_id}`}>Round {past.round}</Link> : `Round ${past.round}`}
                                    {" "}· approved {shortDate(past.approved_at)}{past.reviewer_name ? ` · ${past.reviewer_name}` : ""}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        )}
                        {assignment.pm_reminded_at && <div className="quarter-card-meta">Reminded PM {relativeTime(assignment.pm_reminded_at)}</div>}
                        {assignment.reviewer_reminded_at && <div className="quarter-card-meta">Reminded reviewer {relativeTime(assignment.reviewer_reminded_at)}</div>}
                      </td>
                    </tr>
                  );
                })}
                {notStarted.map((platform) => (
                  <tr key={platform}>
                    <td><div style={{ fontWeight: 600 }}>{platform}</div></td>
                    <td><span className="quarter-card-meta">Not started</span></td>
                    <td />
                    <td />
                    <td>
                      {onAddPlatforms && entry.can_add_platforms && (
                        <button type="button" className="btn btn-ghost" onClick={onAddPlatforms}>Initiate</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rerunFor && (
            <form onSubmit={handleRerun} className="field" style={{ display: "grid", gap: "var(--space-2)" }}>
              <div className="segmented" role="group" aria-label={`Re-run source for ${rerunFor}`}>
                <button type="button" className={`btn btn-sm ${rerunMode === "url" ? "btn-primary" : ""}`} aria-pressed={rerunMode === "url"} onClick={() => setRerunMode("url")}>Use a URL</button>
                <button type="button" className={`btn btn-sm ${rerunMode === "zip" ? "btn-primary" : ""}`} aria-pressed={rerunMode === "zip"} onClick={() => setRerunMode("zip")}>Use a .zip</button>
              </div>
              {rerunMode === "url" ? (
                <>
                  <label htmlFor="rerunUrl">New DevOps URL for {rerunFor}</label>
                  <input id="rerunUrl" className="input" value={rerunUrl} onChange={(event) => setRerunUrl(event.target.value)} autoComplete="off" />
                  <input
                    className="input" aria-label={`Branch for the ${rerunFor} re-run`} placeholder="default branch"
                    value={rerunBranch} onChange={(event) => setRerunBranch(event.target.value)} autoComplete="off"
                  />
                </>
              ) : (
                <>
                  <label htmlFor="rerunZip">New source zip for {rerunFor}</label>
                  <input id="rerunZip" type="file" accept=".zip" className="input" onChange={(event) => setRerunZip(event.target.files[0] ?? null)} />
                </>
              )}
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button type="submit" className="btn btn-primary" disabled={rerunMode === "zip" ? !rerunZip : !rerunUrl.trim()}>Queue re-run</button>
                <button type="button" className="btn" onClick={() => setRerunFor(null)}>Cancel</button>
              </div>
            </form>
          )}
          {reinitFor && (
            <form onSubmit={handleReinitiate} aria-label={`Reinitiate ${reinitFor.platform}`} className="field" style={{ display: "grid", gap: "var(--space-2)" }}>
              <p className="card-body" style={{ margin: 0 }}>
                Start round {reinitFor.round} for {reinitFor.platform}. The approved review stays in the history; the PM is asked for the source again.
              </p>
              <label htmlFor="reinitReviewer">Reviewer for round {reinitFor.round}</label>
              <select id="reinitReviewer" className="input" value={reinitReviewer} onChange={(event) => setReinitReviewer(event.target.value)}>
                <option value="" disabled>Choose…</option>
                {reviewers.map((reviewer) => <option key={reviewer.id} value={reviewer.id}>{reviewer.name || reviewer.email}</option>)}
              </select>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button type="submit" className="btn btn-primary" disabled={!reinitReviewer}>Start round {reinitFor.round}</button>
                <button type="button" className="btn" onClick={() => setReinitFor(null)}>Cancel</button>
              </div>
            </form>
          )}
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

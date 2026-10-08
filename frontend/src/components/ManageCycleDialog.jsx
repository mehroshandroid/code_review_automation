import { useEffect, useState } from "react";
import AssignmentStatusBadge from "./AssignmentStatusBadge";
import { changeAssignmentReviewer, getReviewers, rerunAssignment, retryAssignment } from "../services/api";

export default function ManageCycleDialog({ project, year, entry, onChanged, onClose }) {
  const cycleId = entry.cycle.id;
  const [assignments, setAssignments] = useState(entry.cycle.assignments);
  const [reviewers, setReviewers] = useState([]);
  const [error, setError] = useState("");
  const [rerunFor, setRerunFor] = useState(null);
  const [rerunUrl, setRerunUrl] = useState("");
  const [rerunBranch, setRerunBranch] = useState("");

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
    if (await act(() => rerunAssignment(cycleId, rerunFor, { devopsUrl: rerunUrl.trim(), devopsBranch: rerunBranch.trim() }))) {
      setRerunFor(null);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label="Manage review cycle" style={{ maxWidth: 760 }} onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">Q{entry.quarter} {year} review — {project.name}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead><tr><th>Platform</th><th>Status</th><th>Reviewer</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {assignments.map((assignment) => {
                  const approved = assignment.review_status === "approved";
                  return (
                    <tr key={assignment.platform}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{assignment.platform}</div>
                        <div className="quarter-card-meta" style={{ wordBreak: "break-all" }}>{assignment.devops_url || "No URL yet"}</div>
                      </td>
                      <td>
                        <AssignmentStatusBadge assignment={assignment} />
                        {assignment.run_status === "failed" && assignment.run_error && <div className="run-error">{assignment.run_error}</div>}
                      </td>
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
                      <td style={{ whiteSpace: "nowrap" }}>
                        {assignment.run_status === "failed" && (
                          <button type="button" className="btn btn-ghost" onClick={() => act(() => retryAssignment(cycleId, assignment.platform))}>Retry</button>
                        )}
                        {assignment.run_status === "completed" && !approved && (
                          <button type="button" className="btn btn-ghost" onClick={() => {
                            setRerunFor(assignment.platform);
                            setRerunUrl(assignment.devops_url || "");
                            setRerunBranch(assignment.devops_branch || "");
                          }}>Re-run</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {rerunFor && (
            <form onSubmit={handleRerun} className="field" style={{ display: "grid", gap: "var(--space-2)" }}>
              <label htmlFor="rerunUrl">New DevOps URL for {rerunFor}</label>
              <input id="rerunUrl" className="input" value={rerunUrl} onChange={(event) => setRerunUrl(event.target.value)} autoComplete="off" />
              <input
                className="input" aria-label={`Branch for the ${rerunFor} re-run`} placeholder="default branch"
                value={rerunBranch} onChange={(event) => setRerunBranch(event.target.value)} autoComplete="off"
              />
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button type="submit" className="btn btn-primary" disabled={!rerunUrl.trim()}>Queue re-run</button>
                <button type="button" className="btn" onClick={() => setRerunFor(null)}>Cancel</button>
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

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AssignmentStatusBadge from "./AssignmentStatusBadge";
import { getMyCycles, submitAssignmentUrl } from "../services/api";

const REFRESH_MS = 10000;

function AssignmentRow({ cycleId, assignment, onUpdated }) {
  const editable = assignment.run_status === "waiting_for_url" || assignment.run_status === "failed";
  const [url, setUrl] = useState(assignment.devops_url || "");
  const [branch, setBranch] = useState(assignment.devops_branch || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      onUpdated(await submitAssignmentUrl(cycleId, assignment.platform, { devopsUrl: url.trim(), devopsBranch: branch.trim() }));
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save the URL.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{assignment.platform}</td>
      <td>{assignment.reviewer_name || "—"}</td>
      <td>
        <AssignmentStatusBadge assignment={assignment} />
        {assignment.run_status === "failed" && assignment.run_error && <div className="run-error">{assignment.run_error}</div>}
      </td>
      <td style={{ minWidth: 320 }}>
        {editable ? (
          <form onSubmit={handleSave} className="assignment-url-form">
            <input
              className="input" aria-label={`DevOps URL for ${assignment.platform}`} placeholder="https://dev.azure.com/org/project/_git/repo"
              value={url} onChange={(event) => setUrl(event.target.value)} autoComplete="off" data-1p-ignore data-lpignore="true"
            />
            <input
              className="input" aria-label={`Branch for ${assignment.platform}`} placeholder="default branch"
              value={branch} onChange={(event) => setBranch(event.target.value)} autoComplete="off" style={{ maxWidth: 160 }}
            />
            <button type="submit" className="btn btn-primary" disabled={saving || !url.trim()}>
              {assignment.run_status === "failed" ? "Save & retry" : "Save & queue"}
            </button>
            {error && <p className="run-error" style={{ flexBasis: "100%" }}>{error}</p>}
          </form>
        ) : assignment.run_status === "completed" && assignment.review_id ? (
          <Link to={`/reports/${assignment.review_id}`} className="btn btn-ghost">View</Link>
        ) : (
          <span className="quarter-card-meta" style={{ wordBreak: "break-all" }}>{assignment.devops_url}</span>
        )}
      </td>
    </tr>
  );
}

export default function PendingCyclesPanel() {
  const [cycles, setCycles] = useState(null);

  const load = useCallback(() => {
    getMyCycles().then(setCycles).catch(() => setCycles((current) => current ?? []));
  }, []);

  useEffect(() => { load(); }, [load]);

  const active = (cycles || []).some((cycle) => cycle.assignments.some((a) => a.run_status === "queued" || a.run_status === "running"));
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [active, load]);

  function replaceAssignment(cycleId, updated) {
    setCycles((current) => current.map((cycle) => (cycle.id !== cycleId ? cycle : {
      ...cycle, assignments: cycle.assignments.map((a) => (a.platform === updated.platform ? updated : a)),
    })));
  }

  if (!cycles || cycles.length === 0) return null;

  return (
    <section className="card pending-cycles" aria-label="Pending quarterly reviews">
      <div className="card-kicker">Action needed</div>
      <div className="card-title" style={{ fontSize: 18 }}>Pending quarterly reviews</div>
      <p className="card-body">Add the Azure DevOps repository for each platform. The review runs automatically once saved.</p>
      {cycles.map((cycle) => (
        <div key={cycle.id} className="pending-cycle">
          <div className="pending-cycle-head">
            <span className="pending-cycle-title">{cycle.project_name} · Q{cycle.quarter} {cycle.year} review</span>
            <span className="quarter-card-meta">Initiated {new Date(cycle.initiated_at).toLocaleDateString()}</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table table--padded">
              <thead><tr><th>Platform</th><th>Reviewer</th><th>Status</th><th>Repository</th></tr></thead>
              <tbody>
                {cycle.assignments.map((assignment) => (
                  <AssignmentRow
                    key={`${assignment.platform}-${assignment.run_status}`} cycleId={cycle.id} assignment={assignment}
                    onUpdated={(updated) => replaceAssignment(cycle.id, updated)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}

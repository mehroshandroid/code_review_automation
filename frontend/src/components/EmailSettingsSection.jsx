import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { hasPermission } from "../permissions";
import { getEmailOutbox, getEmailStatus, retryEmail, sendTestEmail } from "../services/api";

const MODE_LABELS = { log: "Log only (no email is sent)", graph: "Microsoft Graph", smtp: "SMTP" };

export default function EmailSettingsSection() {
  const { user } = useAuth();
  const allowed = hasPermission(user, "email.manage");
  const [status, setStatus] = useState(null);
  const [emails, setEmails] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    Promise.all([getEmailStatus(), getEmailOutbox()])
      .then(([nextStatus, nextEmails]) => { setStatus(nextStatus); setEmails(nextEmails); setError(""); })
      .catch(() => setError("Failed to load email settings"));
  }, []);

  useEffect(() => { if (allowed) load(); }, [allowed, load]);

  if (!allowed) return null;

  async function handleTest() {
    setMessage("");
    try {
      await sendTestEmail();
      setMessage(`Test email queued for ${user.email}.`);
      load();
    } catch (err) {
      setMessage(err.response?.data?.detail || "Failed to queue a test email");
    }
  }

  async function handleRetry(id) {
    try {
      await retryEmail(id);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to retry the email");
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">Email</div>
      <div className="card-title" style={{ fontSize: 18 }}>Workflow emails</div>
      {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
      {status && (
        <div className="card-body" style={{ display: "grid", gap: 4 }}>
          <div>Delivery: <strong>{MODE_LABELS[status.mode] || status.mode}</strong>{status.from_address && <> · from {status.from_name} &lt;{status.from_address}&gt;</>}</div>
          <div>Links point to {status.base_url}</div>
          {status.configured ? <div>Configured.</div> : (
            <ul style={{ margin: 0, color: "var(--color-brand-coral)" }}>
              {status.problems.map((problem) => <li key={problem}>{problem}</li>)}
            </ul>
          )}
        </div>
      )}
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" className="btn btn-primary" onClick={handleTest}>Send test email</button>
        <button type="button" className="btn btn-ghost" onClick={load}>Refresh</button>
        {message && <span className="card-body" style={{ margin: 0 }}>{message}</span>}
      </div>
      <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
        {emails.length === 0 ? <p className="card-body">No emails yet.</p> : (
          <table className="table table--padded">
            <thead><tr><th>When</th><th>To</th><th>Subject</th><th>Status</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {emails.map((row) => (
                <tr key={row.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(row.created_at).toLocaleString()}</td>
                  <td>{row.recipient_name || row.recipient_email || "—"}</td>
                  <td>{row.subject || row.event}</td>
                  <td>
                    <span className={`email-status email-status--${row.status}`}>{row.status}</span>
                    {row.last_error && <div className="run-error">{row.last_error}</div>}
                  </td>
                  <td>{row.status === "failed" && <button type="button" className="btn btn-ghost" onClick={() => handleRetry(row.id)}>Retry</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

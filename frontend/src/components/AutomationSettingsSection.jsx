import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { hasPermission } from "../permissions";
import { getAutomationSettings, saveAutoCompileModes, saveDevopsPat } from "../services/api";

const COMPILE_OPTIONS = {
  Android: [["compiler", "Docker lint"], ["local", "Local lint (Mac agent)"], ["static", "Static analysis"]],
  ".NET": [["compiler", "Docker build"], ["static", "Static analysis"]],
  iOS: [["compiler", "Mac build agent"], ["static", "Static analysis"]],
};

function patSummary(pat) {
  if (!pat?.configured) return "Not configured — automatic reviews can't fetch repositories until an admin adds one.";
  const when = pat.updated_at ? ` · updated ${new Date(pat.updated_at).toLocaleDateString()}` : "";
  const by = pat.updated_by_name ? ` by ${pat.updated_by_name}` : "";
  return `Configured · ••••${pat.last4}${when}${by}`;
}

export default function AutomationSettingsSection() {
  const { user } = useAuth();
  const canSetPat = hasPermission(user, "settings.devops_pat");
  const [pat, setPat] = useState(null);
  const [newPat, setNewPat] = useState("");
  const [modes, setModes] = useState(null);
  const [error, setError] = useState("");
  const [patMessage, setPatMessage] = useState("");
  const [modesMessage, setModesMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAutomationSettings()
      .then((result) => { if (!cancelled) { setPat(result.pat); setModes(result.compile_modes); } })
      .catch(() => { if (!cancelled) setError("Failed to load automatic review settings"); });
    return () => { cancelled = true; };
  }, []);

  async function handleSavePat(event) {
    event.preventDefault();
    setPatMessage("");
    try {
      setPat(await saveDevopsPat(newPat.trim()));
      setNewPat("");
      setPatMessage("Saved. Reviews that failed for system reasons were re-queued.");
    } catch (err) {
      setPatMessage(err.response?.data?.detail || "Failed to save the PAT");
    }
  }

  async function handleSaveModes() {
    setModesMessage("");
    try {
      setModes(await saveAutoCompileModes(modes));
      setModesMessage("Saved.");
    } catch (err) {
      setModesMessage(err.response?.data?.detail || "Failed to save compile checks");
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">Automatic reviews</div>
      <div className="card-title" style={{ fontSize: 18 }}>Quarterly cycle runs</div>
      <p className="card-body">Reviews started from a PM's DevOps URL use these settings plus the org-wide LLM provider and sample templates.</p>
      {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

      {pat && (
        <div className="field" style={{ marginTop: "var(--space-3)" }}>
          <label>Azure DevOps PAT</label>
          <p className="card-body" style={{ margin: 0 }}>{patSummary(pat)}</p>
          {canSetPat && (
            <form onSubmit={handleSavePat} style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)", flexWrap: "wrap" }}>
              <input
                type="password" className="input" aria-label="New Azure DevOps PAT" autoComplete="new-password"
                placeholder={pat.configured ? "Replace PAT…" : "Paste PAT…"} value={newPat}
                onChange={(event) => setNewPat(event.target.value)} style={{ maxWidth: 360 }}
                data-1p-ignore data-lpignore="true"
              />
              <button type="submit" className="btn btn-primary" disabled={!newPat.trim()}>Save PAT</button>
            </form>
          )}
          {patMessage && <p className="card-body" style={{ marginTop: "var(--space-2)" }}>{patMessage}</p>}
        </div>
      )}

      {modes && (
        <div className="field" style={{ marginTop: "var(--space-4)" }}>
          <label>Compile check for automatic reviews</label>
          <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginTop: "var(--space-2)" }}>
            {Object.entries(COMPILE_OPTIONS).map(([platform, options]) => (
              <div key={platform} className="field" style={{ minWidth: 180 }}>
                <label htmlFor={`compile-${platform}`} style={{ fontSize: 13 }}>{platform}</label>
                <select
                  id={`compile-${platform}`} aria-label={`Compile check for ${platform}`} className="input"
                  value={modes[platform]} onChange={(event) => setModes((current) => ({ ...current, [platform]: event.target.value }))}
                >
                  {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
            ))}
          </div>
          <button type="button" className="btn btn-primary" style={{ marginTop: "var(--space-3)", alignSelf: "flex-start" }} onClick={handleSaveModes}>
            Save compile checks
          </button>
          {modesMessage && <p className="card-body" style={{ marginTop: "var(--space-2)" }}>{modesMessage}</p>}
        </div>
      )}
    </section>
  );
}

import { useState } from "react";
import { DownloadIcon } from "../icons";
import { getDownloadUrl } from "../services/api";

function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

const TIMING_ROWS = [
  { key: "ingest_time_ms", label: "Ingest (unzip + validate)" },
  { key: "analysis_time_ms", label: "Analysis (parsing + secrets + versions)" },
  { key: "compile_time_ms", label: "Compiling & Lint (Gradle)" },
  { key: "scoring_time_ms", label: "Scoring (Azure OpenAI)" },
  { key: "generation_time_ms", label: "Generation (Excel write)" },
  { key: "total_time_ms", label: "Total" },
];

// Only resets the button-specific UA defaults that would otherwise show
// through (native border/background chrome, OS UI font-family) --
// deliberately leaves padding/font-size/letter-spacing alone so the
// button still picks up .tag's own values, same as the plain-span version.
const TAG_BUTTON_RESET = {
  border: "none",
  background: "none",
  fontFamily: "inherit",
  cursor: "pointer",
};

export default function StatsDisplay({ totalScorePct, warnings, secretsFound, lintIssues, stats, downloadUrl, onReset }) {
  const [activeDialog, setActiveDialog] = useState(null);
  const rows = TIMING_ROWS.filter((row) => stats[row.key] !== undefined);

  // Structural warnings and compile-time lint issues are both just
  // "warnings" from the user's perspective, so they're combined into one
  // count and one popup here rather than split across two tags.
  const lintIssuesList = lintIssues || [];
  const warningsCount = warnings.length + lintIssuesList.length;
  const hasWarnings = warningsCount > 0;
  const hasSecrets = secretsFound.length > 0;

  return (
    <div>
      <div className="card elev-md" style={{ padding: 32 }}>
        <div className="card-kicker">Complete</div>
        <div className="card-title" style={{ fontSize: 22 }}>Review ready</div>
        <p className="card-body">Scores were written into your template with the original formatting preserved.</p>
        <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
          {totalScorePct !== null && totalScorePct !== undefined && (
            <span className="tag tag-accent">Total {totalScorePct}%</span>
          )}
          {hasWarnings ? (
            <button
              type="button"
              className="tag tag-outline"
              style={TAG_BUTTON_RESET}
              onClick={() => setActiveDialog("warnings")}
            >
              {warningsCount} warnings
            </button>
          ) : (
            <span className="tag tag-outline">{warningsCount} warnings</span>
          )}
          {hasSecrets ? (
            <button
              type="button"
              className="tag tag-outline"
              style={TAG_BUTTON_RESET}
              onClick={() => setActiveDialog("secrets")}
            >
              {secretsFound.length} secrets
            </button>
          ) : (
            <span className="tag tag-outline">{secretsFound.length} secrets</span>
          )}
        </div>
        <a
          href={getDownloadUrl(downloadUrl)}
          download
          className="btn btn-primary btn-block"
          style={{ marginTop: "var(--space-5)" }}
        >
          Download populated workbook
          <DownloadIcon />
        </a>
        <button
          type="button"
          className="btn btn-block"
          style={{ marginTop: "var(--space-3)", color: "var(--color-accent)" }}
          onClick={() => setActiveDialog("performance")}
        >
          Performance breakdown
        </button>
      </div>

      {activeDialog === "performance" && (
        <div className="dialog-backdrop" onClick={() => setActiveDialog(null)}>
          <div className="dialog" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">Performance breakdown</div>
            <table className="table dialog-body">
              <thead><tr><th>Phase</th><th>Duration</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    <td className="text-muted">{formatSeconds(stats[row.key])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={() => setActiveDialog(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {activeDialog === "warnings" && (
        <div className="dialog-backdrop" onClick={() => setActiveDialog(null)}>
          <div className="dialog" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">Warnings</div>
            <ul className="dialog-body" style={{ paddingLeft: "1.1em", fontSize: 13 }}>
              {warnings.map((warning, index) => (
                <li key={`structural-${index}`}>{warning}</li>
              ))}
              {lintIssuesList.map((issue, index) => (
                <li key={`lint-${index}`}>{issue.file}:{issue.line} ({issue.severity}): {issue.message}</li>
              ))}
            </ul>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={() => setActiveDialog(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {activeDialog === "secrets" && (
        <div className="dialog-backdrop" onClick={() => setActiveDialog(null)}>
          <div className="dialog" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">Secrets found</div>
            <ul className="dialog-body" style={{ paddingLeft: "1.1em", fontSize: 13 }}>
              {secretsFound.map((secret, index) => (
                <li key={index}>{secret.file}:{secret.line} ({secret.pattern})</li>
              ))}
            </ul>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={() => setActiveDialog(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      <button type="button" className="btn btn-ghost" style={{ marginTop: "var(--space-5)" }} onClick={onReset}>
        Start new review
      </button>
    </div>
  );
}

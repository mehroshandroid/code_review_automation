import CornerMarks from "./CornerMarks";
import FindingsPanel from "./FindingsPanel";
import CategoryScoresChart from "./CategoryScoresChart";
import { DownloadIcon } from "../icons";
import { getDownloadUrl } from "../services/api";

function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

const TIMING_ROWS = [
  { key: "ingest_time_ms", label: "Ingest (unzip + validate)" },
  { key: "analysis_time_ms", label: "Analysis (parsing + secrets + versions)" },
  { key: "scoring_time_ms", label: "Scoring (Azure OpenAI)" },
  { key: "generation_time_ms", label: "Generation (Excel write)" },
  { key: "total_time_ms", label: "Total" },
];

export default function StatsDisplay({
  totalScorePct, warnings, testCoverage, secretsFound, categoryScores, stats, downloadUrl, onReset,
}) {
  const rows = TIMING_ROWS.filter((row) => stats[row.key] !== undefined);

  return (
    <div>
      <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
        <CornerMarks />
        <div className="card-kicker">Complete</div>
        <div className="card-title" style={{ fontSize: 20 }}>Review ready</div>
        <p className="card-body">Scores were written into your template with the original formatting preserved.</p>
        <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
          {totalScorePct !== null && totalScorePct !== undefined && (
            <span className="tag tag-accent">Total {totalScorePct}%</span>
          )}
          <span className="tag tag-outline">{warnings.length} warnings</span>
          <span className="tag tag-outline">{secretsFound.length} secrets</span>
        </div>
        <a
          href={getDownloadUrl(downloadUrl)}
          download
          className="btn btn-primary btn-block blueprint"
          style={{ marginTop: "var(--space-5)" }}
        >
          <CornerMarks />
          Download populated workbook
          <DownloadIcon />
        </a>
      </div>

      <div style={{ marginTop: "var(--space-5)" }}>
        <CategoryScoresChart categoryScores={categoryScores} />
      </div>

      <div style={{ marginTop: "var(--space-5)" }}>
        <FindingsPanel warnings={warnings} testCoverage={testCoverage} secretsFound={secretsFound} />
      </div>

      <div className="card blueprint" style={{ padding: "var(--space-6)", marginTop: "var(--space-5)" }}>
        <CornerMarks />
        <div className="card-kicker">Timing</div>
        <div className="card-title" style={{ fontSize: 20 }}>Performance breakdown</div>
        <table className="table" style={{ marginTop: "var(--space-4)" }}>
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
      </div>

      <button type="button" className="btn btn-ghost" style={{ marginTop: "var(--space-5)" }} onClick={onReset}>
        Start new review
      </button>
    </div>
  );
}

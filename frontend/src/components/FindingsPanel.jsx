import { useState } from "react";

function FindingCard({ kicker, value, caption, expandable, expanded, onToggle, children }) {
  return (
    <div className="card card-subtle" style={{ borderRadius: 14, padding: 18 }}>
      <div className="card-kicker-muted">{kicker}</div>
      <div style={{ fontFamily: "var(--font-heading)", fontWeight: "var(--font-heading-weight)", fontSize: 28, margin: "6px 0" }}>{value}</div>
      {expandable ? (
        <button
          type="button"
          className="card-body"
          style={{ textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit", fontSize: 13 }}
          onClick={onToggle}
        >
          {caption}
        </button>
      ) : (
        <p className="card-body" style={{ fontSize: 13 }}>{caption}</p>
      )}
      {expanded && children}
    </div>
  );
}

function lintCardProps(compileStatus, lintIssues) {
  if (compileStatus === "ok") {
    return lintIssues.length > 0
      ? { value: lintIssues.length, caption: `${lintIssues.length} issue${lintIssues.length === 1 ? "" : "s"} found`, expandable: true }
      : { value: 0, caption: "No Lint warnings or errors found.", expandable: false };
  }
  if (compileStatus === "build_failed") {
    return { value: "—", caption: "Project failed to compile.", expandable: false };
  }
  if (compileStatus === "unavailable") {
    return { value: "—", caption: "Compile check unavailable.", expandable: false };
  }
  if (compileStatus === "skipped") {
    return { value: "—", caption: "Static analysis mode selected — clause 1.4 scored by AI.", expandable: false };
  }
  return { value: "—", caption: "Not yet checked.", expandable: false };
}

export default function FindingsPanel({ warnings, testCoverage, secretsFound, lintIssues, compileStatus }) {
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [secretsOpen, setSecretsOpen] = useState(false);
  const [lintOpen, setLintOpen] = useState(false);

  const hasWarnings = warnings && warnings.length > 0;
  const hasSecrets = secretsFound && secretsFound.length > 0;
  const hasCoverage = testCoverage !== null && testCoverage !== undefined;
  const hasLintStatus = compileStatus !== null && compileStatus !== undefined;

  if (!hasWarnings && !hasSecrets && !hasCoverage && !hasLintStatus) {
    return null;
  }

  const lint = lintCardProps(compileStatus, lintIssues || []);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "var(--space-4)" }}>
      <FindingCard
        kicker="Warnings"
        value={warnings.length}
        caption={hasWarnings ? `${warnings.length} issue${warnings.length === 1 ? "" : "s"} found` : "No warnings found."}
        expandable={hasWarnings}
        expanded={warningsOpen}
        onToggle={() => setWarningsOpen((open) => !open)}
      >
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--color-text-muted)" }}>
          {warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      </FindingCard>

      <FindingCard
        kicker="Test coverage"
        value={hasCoverage ? `${testCoverage}%` : "—"}
        caption={hasCoverage ? "Coverage report found." : "No coverage report found."}
        expandable={false}
      />

      <FindingCard
        kicker="Secrets found"
        value={secretsFound.length}
        caption={hasSecrets ? `${secretsFound.length} possible secret${secretsFound.length === 1 ? "" : "s"} found` : "No secrets found."}
        expandable={hasSecrets}
        expanded={secretsOpen}
        onToggle={() => setSecretsOpen((open) => !open)}
      >
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--color-text-muted)" }}>
          {secretsFound.map((secret, index) => (
            <li key={index}>{secret.file}:{secret.line} ({secret.pattern})</li>
          ))}
        </ul>
      </FindingCard>

      <FindingCard
        kicker="Lint issues"
        value={lint.value}
        caption={lint.caption}
        expandable={lint.expandable}
        expanded={lintOpen}
        onToggle={() => setLintOpen((open) => !open)}
      >
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--color-text-muted)" }}>
          {(lintIssues || []).map((issue, index) => (
            <li key={index}>{issue.file}:{issue.line} ({issue.severity}): {issue.message}</li>
          ))}
        </ul>
      </FindingCard>
    </div>
  );
}

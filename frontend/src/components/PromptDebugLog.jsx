import { useState } from "react";

function tokenSummary(tokens) {
  if (!tokens) return "";
  const parts = [
    `${tokens.prompt_tokens ?? 0} prompt`,
    `${tokens.completion_tokens ?? 0} completion`,
    `${tokens.total_tokens ?? 0} total`,
  ];
  if (tokens.cached_tokens) parts.push(`${tokens.cached_tokens} cached`);
  return parts.join(" · ");
}

export default function PromptDebugLog({ codeContext, promptLog }) {
  const [codeOpen, setCodeOpen] = useState(false);

  return (
    <div className="card" style={{ padding: 20, maxHeight: 420, overflowY: "auto" }}>
      <div className="card-title" style={{ fontSize: 18 }}>Prompts &amp; token usage</div>

      <button
        type="button"
        style={{
          textAlign: "left", background: "none", border: "none", padding: 0,
          cursor: "pointer", font: "inherit", fontSize: 13, color: "var(--color-accent)",
          marginTop: "var(--space-3)",
        }}
        onClick={() => setCodeOpen((open) => !open)}
      >
        {codeOpen ? "Hide" : "Show"} source code sent to the model
      </button>
      {codeOpen && (
        <pre
          style={{
            whiteSpace: "pre-wrap", fontSize: 12, maxHeight: 200, overflowY: "auto",
            background: "var(--color-surface)", padding: "var(--space-2)", marginTop: "var(--space-2)",
          }}
        >
          {codeContext}
        </pre>
      )}

      <div style={{ marginTop: "var(--space-4)", display: "grid", gap: "var(--space-3)" }}>
        {promptLog.map((entry, index) => (
          <div key={index} style={{ borderTop: "1px solid var(--color-divider)", paddingTop: "var(--space-2)" }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{entry.label}</div>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: "var(--space-1) 0" }}>{entry.prompt_text}</pre>
            <p className="text-muted" style={{ fontSize: 11, margin: 0 }}>{tokenSummary(entry.tokens)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function sumTokens(promptLog) {
  return promptLog.reduce((total, entry) => total + (entry.tokens?.total_tokens ?? 0), 0);
}

export default function LlmUsageStats({ promptLog }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
      <span className="tag tag-outline">{promptLog.length} LLM calls</span>
      <span className="tag tag-outline">{sumTokens(promptLog)} tokens used</span>
    </div>
  );
}

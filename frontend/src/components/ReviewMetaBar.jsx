const COMPILE_CHECK_LABELS = {
  compiler: "Docker",
  local: "Local",
  static: "Static",
};

export default function ReviewMetaBar({ llmProvider, llmModel, source, compileCheckMode }) {
  const llmLabel = llmProvider === "ollama" ? `Ollama (${llmModel})` : "Azure OpenAI";
  const sourceLabel = source === "devops" ? "Azure DevOps" : "Uploaded ZIP";
  const compileCheckLabel = COMPILE_CHECK_LABELS[compileCheckMode] || "Static";

  return (
    <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", alignItems: "center" }}>
      <span className="tag tag-outline">{llmLabel}</span>
      <span className="tag tag-outline">{sourceLabel}</span>
      <span className="tag tag-outline">Compile-check: {compileCheckLabel}</span>
    </div>
  );
}

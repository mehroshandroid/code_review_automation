const COMPILE_CHECK_LABELS = {
  compiler: "Docker",
  local: "Local",
  static: "Static",
};

const LLM_LABELS = {
  ollama: (llmModel) => `Ollama (${llmModel})`,
  claude: () => "Claude CLI (local)",
};

export default function ReviewMetaBar({ llmProvider, llmModel, source, compileCheckMode }) {
  const llmLabel = (LLM_LABELS[llmProvider] || (() => "Azure OpenAI"))(llmModel);
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

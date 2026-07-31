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
    <p className="card-body" style={{ margin: "0 0 var(--space-5)", opacity: 0.75, fontSize: 13 }}>
      {llmLabel} · {sourceLabel} · Compile-check: {compileCheckLabel}
    </p>
  );
}

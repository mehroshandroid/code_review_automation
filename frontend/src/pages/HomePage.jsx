import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import CornerMarks from "../components/CornerMarks";
import { PLATFORMS } from "../platforms";
import { getOllamaModels } from "../services/api";
import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel } from "../services/llmProviderStorage";

const LLM_PROVIDERS = [
  { id: "azure", label: "Azure OpenAI" },
  { id: "ollama", label: "Ollama (local)" },
];

export default function HomePage() {
  const [llmProvider, setLlmProviderState] = useState(() => getLlmProvider());
  const [ollamaModel, setOllamaModelState] = useState(() => getOllamaModel());
  const [ollamaModels, setOllamaModels] = useState(null); // null = still loading

  useEffect(() => {
    let cancelled = false;
    getOllamaModels()
      .then((models) => { if (!cancelled) setOllamaModels(models); })
      .catch(() => { if (!cancelled) setOllamaModels([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!ollamaModels || ollamaModels.length === 0) return;
    const initial = ollamaModels.includes(ollamaModel) ? ollamaModel : ollamaModels[0];
    if (initial !== ollamaModel) {
      setOllamaModel(initial);
      setOllamaModelState(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ollamaModels]);

  function handleSelectProvider(providerId) {
    setLlmProvider(providerId);
    setLlmProviderState(providerId);
  }

  function handleSelectModel(model) {
    setOllamaModel(model);
    setOllamaModelState(model);
  }

  const ollamaEnabled = ollamaModels === null || ollamaModels.length > 0;
  const effectiveProvider = !ollamaEnabled && llmProvider === "ollama" ? "azure" : llmProvider;

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav"><span className="nav-brand">Code Review Automation</span></nav>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            Code Review Automation
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Choose a platform to start a review.
          </p>
        </header>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
          {PLATFORMS.map((platform) => (
            <Link
              key={platform.id}
              to={`/review/${platform.id}`}
              className="card blueprint elev-md"
              style={{ padding: "var(--space-6)", textDecoration: "none", color: "inherit" }}
            >
              <CornerMarks />
              <div className="card-kicker">{platform.available ? "Available" : "Coming soon"}</div>
              <div className="card-title" style={{ fontSize: 20 }}>{platform.label}</div>
            </Link>
          ))}
        </div>

        <div className="card blueprint" style={{ padding: "var(--space-6)", marginTop: "var(--space-6)" }}>
          <CornerMarks />
          <div className="card-kicker">LLM provider</div>
          <div className="card-title" style={{ fontSize: 20 }}>Choose a model provider</div>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
            {LLM_PROVIDERS.map((provider) => {
              const disabled = provider.id === "ollama" && !ollamaEnabled;
              return (
                <button
                  key={provider.id}
                  type="button"
                  className={`btn ${effectiveProvider === provider.id ? "btn-primary" : ""}`}
                  disabled={disabled}
                  onClick={() => handleSelectProvider(provider.id)}
                >
                  {provider.label}
                </button>
              );
            })}
          </div>
          {effectiveProvider === "ollama" && ollamaModels && ollamaModels.length > 0 && (
            <select
              aria-label="Ollama model"
              value={ollamaModel || ollamaModels[0]}
              onChange={(event) => handleSelectModel(event.target.value)}
              className="input"
              style={{ marginTop: "var(--space-3)" }}
            >
              {ollamaModels.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
          )}
        </div>
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
      <nav className="nav">
        <span className="logo-mark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="nav-brand">Code Review Automation</span>
      </nav>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "64px 24px 96px" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontWeight: "var(--font-heading-weight)", fontSize: 40, lineHeight: 1.1, letterSpacing: "-0.02em", margin: "0 0 12px" }}>
            Code Review Automation
          </h1>
          <p style={{ margin: 0, color: "var(--color-text-muted)", maxWidth: "60ch", fontSize: 16, lineHeight: 1.6 }}>
            Choose a platform to start a review.
          </p>
        </header>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
          {PLATFORMS.map((platform) => (
            <Link
              key={platform.id}
              to={`/review/${platform.id}`}
              className="card elev-sm"
              style={{ padding: 28, textDecoration: "none", color: "inherit" }}
            >
              <span
                style={{
                  display: "inline-flex", alignSelf: "flex-start", fontSize: 11, fontWeight: 700,
                  letterSpacing: "0.06em", textTransform: "uppercase", padding: "4px 10px", borderRadius: 999,
                  background: platform.available ? "#EAF0F7" : "#F1F2F4",
                  color: platform.available ? "var(--color-accent)" : "var(--color-text-faint)",
                }}
              >
                {platform.available ? "Available" : "Coming soon"}
              </span>
              <div className="card-title" style={{ fontSize: 20, marginTop: 2 }}>{platform.label}</div>
            </Link>
          ))}
        </div>

        <div className="card card-subtle" style={{ padding: 28, marginTop: "var(--space-6)" }}>
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

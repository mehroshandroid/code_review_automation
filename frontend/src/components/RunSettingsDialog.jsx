import { useEffect, useState } from "react";
import { COMPILE_OPTIONS } from "./AutomationSettingsSection";
import { getOllamaModels, saveQueueItemSettings } from "../services/api";

export const PROVIDER_LABELS = { azure: "Azure OpenAI", ollama: "Ollama (local)", claude: "Claude CLI (local)" };

function compileLabel(platform, mode) {
  return (COMPILE_OPTIONS[platform] || []).find(([value]) => value === mode)?.[1] || mode;
}

export default function RunSettingsDialog({ item, defaults, onSaved, onClose }) {
  const [provider, setProvider] = useState(item.override_llm_provider || "");
  const [model, setModel] = useState(item.override_llm_model || "");
  const [compile, setCompile] = useState(item.override_compile_mode || "");
  const [models, setModels] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (provider !== "ollama" || models !== null) return undefined;
    let cancelled = false;
    getOllamaModels().then((result) => { if (!cancelled) setModels(result); }).catch(() => { if (!cancelled) setModels([]); });
    return () => { cancelled = true; };
  }, [provider, models]);

  async function save(settings) {
    setSaving(true);
    setError("");
    try {
      await saveQueueItemSettings(item.cycle_id, item.platform, settings);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save run settings.");
    } finally {
      setSaving(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    save({ llmProvider: provider || null, llmModel: provider === "ollama" ? (model.trim() || null) : null, compileMode: compile || null });
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" role="dialog" aria-label="Run settings" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Run settings — {item.project_name} · {item.platform} · Q{item.quarter} {item.year}</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <p className="card-body" style={{ margin: 0 }}>Applies to this review only, including retries. Leave a field on the org default to use Settings.</p>
          <div className="field">
            <label htmlFor="runProvider">LLM provider</label>
            <select id="runProvider" className="input" value={provider} onChange={(event) => setProvider(event.target.value)}>
              <option value="">Org default ({PROVIDER_LABELS[defaults.llm_provider] || defaults.llm_provider})</option>
              {Object.entries(PROVIDER_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {provider === "ollama" && (
            <div className="field">
              <label htmlFor="runModel">Ollama model</label>
              {models && models.length > 0 ? (
                <select id="runModel" className="input" value={model} onChange={(event) => setModel(event.target.value)}>
                  <option value="">Choose a model…</option>
                  {models.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              ) : (
                <input id="runModel" className="input" value={model} onChange={(event) => setModel(event.target.value)} placeholder="qwen2.5-coder:7b" />
              )}
            </div>
          )}
          <div className="field">
            <label htmlFor="runCompile">Compile check</label>
            <select id="runCompile" className="input" value={compile} onChange={(event) => setCompile(event.target.value)}>
              <option value="">Org default ({compileLabel(item.platform, defaults.compile_modes[item.platform])})</option>
              {(COMPILE_OPTIONS[item.platform] || []).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" disabled={saving} onClick={() => save({ llmProvider: null, llmModel: null, compileMode: null })}>Clear overrides</button>
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}

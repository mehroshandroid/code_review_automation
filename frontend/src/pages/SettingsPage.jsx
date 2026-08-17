import { useEffect, useState } from "react";
import TopNav from "../components/TopNav";
import { PLATFORMS } from "../platforms";
import {
  getLlmProviderSettings, updateLlmProviderSettings, getOllamaModels,
  getClauseChecklists, upsertClauseChecklist, deleteClauseChecklist,
  getSampleTemplates, uploadSampleTemplate, deleteSampleTemplate, previewSampleTemplate,
} from "../services/api";

const PLATFORM_LABELS = PLATFORMS.map((platform) => platform.label);

const LLM_PROVIDERS = [
  { id: "azure", label: "Azure OpenAI" },
  { id: "ollama", label: "Ollama (local)" },
];

function ClausePreviewDialog({ platform, onSelect, onClose }) {
  const [categories, setCategories] = useState(null); // null = still loading
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setCategories(null);
    setError("");
    previewSampleTemplate(platform)
      .then((result) => { if (!cancelled) setCategories(result); })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err.response?.status === 404
            ? `No sample sheet uploaded for ${platform} yet -- upload one below to preview its clauses here.`
            : "Could not read this sheet's clause structure."
        );
      });
    return () => { cancelled = true; };
  }, [platform]);

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">{platform} clauses</div>
        <div className="dialog-body">
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
          {!error && categories === null && <p className="card-body">Loading…</p>}
          {!error && categories && categories.length === 0 && <p className="card-body">This sheet has no recognizable clause structure.</p>}
          {!error && categories && categories.map((category) => (
            <div key={category.id} style={{ marginBottom: "var(--space-4)" }}>
              <div className="card-kicker-muted">{category.id} — {category.name}</div>
              <ul style={{ paddingLeft: "1.1em", fontSize: 13, margin: "6px 0 0" }}>
                {category.sub_criteria.map((sub) => (
                  <li key={sub.id} style={{ marginBottom: "var(--space-2)", display: "flex", alignItems: "baseline", gap: "var(--space-2)" }}>
                    <span><strong>{sub.id}</strong> — {sub.description}</span>
                    {onSelect && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ flexShrink: 0 }}
                        onClick={() => onSelect(sub.id)}
                      >
                        Use
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

function LlmProviderSection() {
  const [provider, setProvider] = useState(null);
  const [ollamaModel, setOllamaModel] = useState("");
  const [ollamaModels, setOllamaModels] = useState(null); // null = still loading
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getLlmProviderSettings()
      .then((settings) => {
        if (cancelled) return;
        setProvider(settings.default_llm_provider);
        setOllamaModel(settings.default_ollama_model || "");
      })
      .catch(() => { if (!cancelled) setError("Failed to load LLM provider settings"); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getOllamaModels()
      .then((models) => { if (!cancelled) setOllamaModels(models); })
      .catch(() => { if (!cancelled) setOllamaModels([]); });
    return () => { cancelled = true; };
  }, []);

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await updateLlmProviderSettings(provider, provider === "ollama" ? (ollamaModel.trim() || null) : null);
      setSaved(true);
    } catch (err) {
      setError("Failed to save LLM provider settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">LLM provider</div>
      <div className="card-title" style={{ fontSize: 18 }}>Organization-wide default</div>
      <p className="card-body">Used whenever a reviewer hasn't picked a provider for their session yet.</p>

      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", flexWrap: "wrap" }}>
        {LLM_PROVIDERS.map((option) => (
          <button
            key={option.id}
            type="button"
            className={`btn ${provider === option.id ? "btn-primary" : ""}`}
            onClick={() => setProvider(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {provider === "ollama" && ollamaModels && ollamaModels.length > 0 && (
        <div className="field" style={{ marginTop: "var(--space-3)" }}>
          <label htmlFor="defaultOllamaModel">Default Ollama model</label>
          <select
            id="defaultOllamaModel"
            className="input"
            value={ollamaModels.includes(ollamaModel) ? ollamaModel : ""}
            onChange={(event) => setOllamaModel(event.target.value)}
          >
            <option value="" disabled>Select a model…</option>
            {ollamaModels.map((model) => <option key={model} value={model}>{model}</option>)}
          </select>
        </div>
      )}

      {provider === "ollama" && ollamaModels && ollamaModels.length === 0 && (
        <div className="field" style={{ marginTop: "var(--space-3)" }}>
          <label htmlFor="defaultOllamaModel">Default Ollama model</label>
          <input
            id="defaultOllamaModel"
            type="text"
            className="input"
            value={ollamaModel}
            onChange={(event) => setOllamaModel(event.target.value)}
            placeholder="qwen2.5-coder:7b"
          />
          <p className="card-body" style={{ marginTop: "var(--space-2)" }}>
            Couldn't reach Ollama to list installed models -- enter the model name manually.
          </p>
        </div>
      )}

      {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
      {saved && <p className="card-body">Saved.</p>}

      <button
        type="button"
        className="btn btn-primary"
        style={{ marginTop: "var(--space-3)", alignSelf: "flex-start" }}
        disabled={saving || !provider}
        onClick={handleSave}
      >
        {saving ? "Saving…" : "Save"}
      </button>
    </section>
  );
}

function ClauseChecklistSection() {
  const [checklists, setChecklists] = useState([]);
  const [platform, setPlatform] = useState(PLATFORM_LABELS[0]);
  const [subId, setSubId] = useState("");
  const [checklistText, setChecklistText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);

  function loadChecklists() {
    return getClauseChecklists().then(setChecklists).catch(() => setError("Failed to load clause checklists"));
  }

  useEffect(() => {
    loadChecklists();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function resetForm() {
    setSubId("");
    setChecklistText("");
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await upsertClauseChecklist(platform, subId.trim(), checklistText.trim());
      resetForm();
      await loadChecklists();
    } catch (err) {
      setError("Failed to save checklist");
    } finally {
      setSaving(false);
    }
  }

  function handleEdit(checklist) {
    setPlatform(checklist.platform);
    setSubId(checklist.sub_id);
    setChecklistText(checklist.checklist_text);
  }

  async function handleDelete(checklist) {
    setError("");
    try {
      await deleteClauseChecklist(checklist.platform, checklist.sub_id);
      await loadChecklists();
    } catch (err) {
      setError("Failed to delete checklist");
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">Per-clause checklists</div>
      <div className="card-title" style={{ fontSize: 18 }}>Clause checklists</div>
      <p className="card-body">Extra, platform-specific things the LLM should specifically check for on a given sub-clause.</p>

      {checklists.length === 0 ? (
        <p className="card-body">No clause checklists configured yet.</p>
      ) : (
        <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Platform</th>
                <th>Sub-clause</th>
                <th>Checklist</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {checklists.map((checklist) => (
                <tr key={`${checklist.platform}-${checklist.sub_id}`}>
                  <td>{checklist.platform}</td>
                  <td>{checklist.sub_id}</td>
                  <td style={{ maxWidth: 480 }}>{checklist.checklist_text}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button type="button" className="btn" onClick={() => handleEdit(checklist)}>Edit</button>
                    <button
                      type="button"
                      className="btn"
                      style={{ marginLeft: "var(--space-2)" }}
                      onClick={() => handleDelete(checklist)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
          <div className="field">
            <label htmlFor="checklistPlatform">Platform</label>
            <select
              id="checklistPlatform"
              className="input"
              value={platform}
              onChange={(event) => setPlatform(event.target.value)}
            >
              {PLATFORM_LABELS.map((label) => <option key={label} value={label}>{label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="checklistSubId">Sub-clause ID</label>
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <input
                id="checklistSubId"
                type="text"
                className="input"
                value={subId}
                onChange={(event) => setSubId(event.target.value)}
                placeholder="2.4"
              />
              <button type="button" className="btn" style={{ flexShrink: 0 }} onClick={() => setPreviewOpen(true)}>
                Preview clauses
              </button>
            </div>
          </div>
        </div>
        <div className="field">
          <label htmlFor="checklistText">Checklist text</label>
          <textarea
            id="checklistText"
            className="input"
            rows={3}
            value={checklistText}
            onChange={(event) => setChecklistText(event.target.value)}
          />
        </div>
        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
        <button
          type="submit"
          className="btn btn-primary"
          style={{ alignSelf: "flex-start" }}
          disabled={saving || !subId.trim() || !checklistText.trim()}
        >
          {saving ? "Saving…" : "Save checklist"}
        </button>
      </form>

      {previewOpen && (
        <ClausePreviewDialog
          platform={platform}
          onSelect={(selectedSubId) => { setSubId(selectedSubId); setPreviewOpen(false); }}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </section>
  );
}

function SampleTemplateSection() {
  const [templates, setTemplates] = useState([]);
  const [uploadingPlatform, setUploadingPlatform] = useState(null);
  const [error, setError] = useState("");
  const [previewPlatform, setPreviewPlatform] = useState(null);

  function loadTemplates() {
    return getSampleTemplates().then(setTemplates).catch(() => setError("Failed to load sample templates"));
  }

  useEffect(() => {
    loadTemplates();
  }, []);

  function templateFor(platformLabel) {
    return templates.find((template) => template.platform === platformLabel);
  }

  async function handleUpload(platformLabel, file) {
    setError("");
    setUploadingPlatform(platformLabel);
    try {
      await uploadSampleTemplate(platformLabel, file);
      await loadTemplates();
    } catch (err) {
      setError(`Failed to upload template for ${platformLabel}`);
    } finally {
      setUploadingPlatform(null);
    }
  }

  async function handleDelete(platformLabel) {
    setError("");
    try {
      await deleteSampleTemplate(platformLabel);
      await loadTemplates();
    } catch (err) {
      setError(`Failed to remove template for ${platformLabel}`);
    }
  }

  return (
    <section className="card elev-sm" style={{ padding: 20 }}>
      <div className="card-kicker">Sample review sheets</div>
      <div className="card-title" style={{ fontSize: 18 }}>Per-platform template defaults</div>
      <p className="card-body">Used when a reviewer starts a review without uploading their own Excel template.</p>

      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
        {PLATFORM_LABELS.map((platformLabel) => {
          const template = templateFor(platformLabel);
          return (
            <div
              key={platformLabel}
              className="card card-subtle"
              style={{ padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)", flexWrap: "wrap" }}
            >
              <div>
                <div className="card-title" style={{ fontSize: 15 }}>{platformLabel}</div>
                <p className="card-body">
                  {template ? `Current default: ${template.filename}` : "No default configured"}
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <label className="btn" style={{ cursor: "pointer" }}>
                  {uploadingPlatform === platformLabel ? "Uploading…" : (template ? "Replace" : "Upload")}
                  <input
                    type="file"
                    accept=".xlsx"
                    aria-label={`Upload sample template for ${platformLabel}`}
                    style={{ display: "none" }}
                    disabled={uploadingPlatform === platformLabel}
                    onChange={(event) => {
                      const file = event.target.files[0];
                      event.target.value = "";
                      if (file) handleUpload(platformLabel, file);
                    }}
                  />
                </label>
                {template && (
                  <button type="button" className="btn" onClick={() => setPreviewPlatform(platformLabel)}>
                    Preview
                  </button>
                )}
                {template && (
                  <button type="button" className="btn" onClick={() => handleDelete(platformLabel)}>
                    Remove
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-3)" }}>{error}</p>}

      {previewPlatform && (
        <ClausePreviewDialog platform={previewPlatform} onClose={() => setPreviewPlatform(null)} />
      )}
    </section>
  );
}

export default function SettingsPage() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />
      <main style={{ maxWidth: 960, margin: "0 auto", padding: "64px 24px 96px", display: "grid", gap: "var(--space-6)" }}>
        <header>
          <h1 style={{ fontFamily: "var(--font-heading)", fontWeight: "var(--font-heading-weight)", fontSize: 32, lineHeight: 1.1, letterSpacing: "-0.02em", margin: "0 0 12px" }}>
            Settings
          </h1>
          <p style={{ margin: 0, color: "var(--color-text-muted)", maxWidth: "60ch", fontSize: 16, lineHeight: 1.6 }}>
            Organization-wide defaults for LLM provider, per-clause checklists, and sample review sheets.
          </p>
        </header>

        <LlmProviderSection />
        <ClauseChecklistSection />
        <SampleTemplateSection />
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import SearchableSelect from "./SearchableSelect";
import ProjectDialog from "./ProjectDialog";
import { PLATFORMS } from "../platforms";
import { createProject, getOllamaModels } from "../services/api";
import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel } from "../services/llmProviderStorage";

const LLM_PROVIDERS = [
  { id: "azure", label: "Azure OpenAI" },
  { id: "ollama", label: "Ollama (local)" },
];

export default function StartReviewDialog({ projects, onProjectCreated, onClose }) {
  const [projectId, setProjectId] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [llmProvider, setLlmProviderState] = useState(() => getLlmProvider());
  const [ollamaModel, setOllamaModelState] = useState(() => getOllamaModel());
  const [ollamaModels, setOllamaModels] = useState(null); // null = still loading
  const navigate = useNavigate();

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

  const ollamaEnabled = ollamaModels === null || ollamaModels.length > 0;
  const effectiveProvider = !ollamaEnabled && llmProvider === "ollama" ? "azure" : llmProvider;

  function handleSelectProvider(providerId) {
    setLlmProvider(providerId);
    setLlmProviderState(providerId);
  }

  function handleSelectModel(model) {
    setOllamaModel(model);
    setOllamaModelState(model);
  }

  async function handleCreateProject(name) {
    const project = await createProject(name);
    onProjectCreated(project);
    setProjectId(project.id);
  }

  function handleSelectPlatform(platform) {
    if (!projectId || !platform.available) return;
    navigate(`/review/${platform.id}`, { state: { projectId } });
  }

  const projectOptions = projects.map((p) => ({ value: p.id, label: p.name }));

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="dialog-title">Start a review</div>
        <div className="dialog-body" style={{ display: "grid", gap: "var(--space-4)" }}>
          <div className="field">
            <label htmlFor="startReviewProject">Project</label>
            <SearchableSelect
              ariaLabel="Project" options={projectOptions} value={projectId} onChange={setProjectId}
              placeholder="Choose a project…" onAddNew={() => setShowCreateDialog(true)} addNewLabel="+ Add new project"
            />
          </div>

          <div className="field">
            <label>LLM provider</label>
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              {LLM_PROVIDERS.map((provider) => {
                const disabled = provider.id === "ollama" && !ollamaEnabled;
                return (
                  <button
                    key={provider.id} type="button"
                    className={`btn ${effectiveProvider === provider.id ? "btn-primary" : ""}`}
                    disabled={disabled} onClick={() => handleSelectProvider(provider.id)}
                  >
                    {provider.label}
                  </button>
                );
              })}
            </div>
            {effectiveProvider === "ollama" && ollamaModels && ollamaModels.length > 0 && (
              <select
                aria-label="Ollama model" value={ollamaModel || ollamaModels[0]}
                onChange={(event) => handleSelectModel(event.target.value)} className="input" style={{ marginTop: "var(--space-3)" }}
              >
                {ollamaModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            )}
          </div>

          <div className="field">
            <label>Platform</label>
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              {PLATFORMS.map((platform) => (
                <div
                  key={platform.id}
                  role="button"
                  aria-label={platform.label}
                  tabIndex={0}
                  className="card elev-sm"
                  style={{
                    padding: 16,
                    cursor: projectId && platform.available ? "pointer" : "not-allowed",
                    opacity: platform.available ? 1 : 0.5,
                  }}
                  onClick={() => handleSelectPlatform(platform)}
                >
                  <div className="card-title" style={{ fontSize: 16 }}>{platform.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>

      {showCreateDialog && (
        <ProjectDialog
          title="New project" initialName="" submitLabel="Create"
          onSubmit={handleCreateProject} onClose={() => setShowCreateDialog(false)}
        />
      )}
    </div>
  );
}

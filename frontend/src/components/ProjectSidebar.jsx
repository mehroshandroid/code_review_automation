import { useState } from "react";
import { createProject, updateProject } from "../services/api";

function ProjectDialog({ title, initialName, submitLabel, onSubmit, onClose }) {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      await onSubmit(name.trim());
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">{title}</div>
        <div className="dialog-body">
          <div className="field">
            <label htmlFor="projectDialogName">Project name</label>
            <input
              id="projectDialogName"
              type="text"
              className="input"
              value={name}
              autoFocus
              disabled={saving}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
            {saving ? "Saving…" : submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function ProjectSidebar({ projects, selectedProjectId, onSelectProject, onProjectCreated, onProjectRenamed }) {
  const [dialog, setDialog] = useState(null); // null | "create" | { renaming: project }

  async function handleCreate(name) {
    const project = await createProject(name);
    onProjectCreated(project);
  }

  async function handleRename(project, name) {
    const updated = await updateProject(project.id, name);
    onProjectRenamed(updated);
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div className="card" style={{ padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
          <div className="card-kicker-muted">Projects</div>
          <button
            type="button"
            className="btn btn-ghost"
            aria-label="Add project"
            style={{ fontSize: 18, lineHeight: 1, padding: "0 6px" }}
            onClick={() => setDialog("create")}
          >
            +
          </button>
        </div>
        {projects.length === 0 ? (
          <p className="card-body">No projects yet -- click + to create one.</p>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {projects.map((project) => (
              <div key={project.id} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <button
                  type="button"
                  className={`btn ${selectedProjectId === project.id ? "btn-primary" : ""}`}
                  style={{ justifyContent: "flex-start", flex: 1, minWidth: 0 }}
                  onClick={() => onSelectProject(project.id)}
                >
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{project.name}</span>
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  aria-label={`Rename ${project.name}`}
                  style={{ padding: "0 6px", flexShrink: 0 }}
                  onClick={() => setDialog({ renaming: project })}
                >
                  ✎
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {dialog === "create" && (
        <ProjectDialog
          title="New project"
          initialName=""
          submitLabel="Create"
          onSubmit={handleCreate}
          onClose={() => setDialog(null)}
        />
      )}

      {dialog && dialog.renaming && (
        <ProjectDialog
          title="Rename project"
          initialName={dialog.renaming.name}
          submitLabel="Save"
          onSubmit={(name) => handleRename(dialog.renaming, name)}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

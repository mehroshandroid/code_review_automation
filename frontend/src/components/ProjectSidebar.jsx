import { useState } from "react";
import { createProject } from "../services/api";

export default function ProjectSidebar({ projects, selectedProjectId, onSelectProject, onProjectCreated }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  async function handleCreate(event) {
    event.preventDefault();
    setError("");
    setCreating(true);
    try {
      const project = await createProject(name.trim());
      onProjectCreated(project);
      setName("");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div className="card" style={{ padding: 20 }}>
        <div className="card-kicker-muted" style={{ marginBottom: "var(--space-3)" }}>Projects</div>
        {projects.length === 0 ? (
          <p className="card-body">No projects yet -- create one below.</p>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                className={`btn ${selectedProjectId === project.id ? "btn-primary" : ""}`}
                style={{ justifyContent: "flex-start" }}
                onClick={() => onSelectProject(project.id)}
              >
                {project.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <form onSubmit={handleCreate} className="card" style={{ padding: 20 }}>
        <div className="card-title" style={{ fontSize: 16, marginBottom: "var(--space-3)" }}>New project</div>
        <div className="field">
          <label htmlFor="sidebarProjectName">Project name</label>
          <input
            id="sidebarProjectName"
            type="text"
            className="input"
            value={name}
            disabled={creating}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{error}</p>}
        <button
          type="submit"
          className="btn btn-primary"
          style={{ marginTop: "var(--space-3)" }}
          disabled={creating || !name.trim()}
        >
          Create
        </button>
      </form>
    </div>
  );
}

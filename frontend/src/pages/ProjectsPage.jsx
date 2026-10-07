import { useEffect, useMemo, useState } from "react";
import AppNav from "../components/AppNav";
import ProjectDialog from "../components/ProjectDialog";
import AssignManagersDialog, { managerLabel } from "../components/AssignManagersDialog";
import { useCan } from "../context/AuthContext";
import { createProject, deleteProject, getProjectManagers, getProjects, setProjectPlatforms, updateProject } from "../services/api";

export default function ProjectsPage() {
  const can = useCan();
  const [projects, setProjects] = useState(null);
  const [managers, setManagers] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState(null);
  const [assigning, setAssigning] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getProjects()
      .then((result) => { if (!cancelled) setProjects(result); })
      .catch(() => { if (!cancelled) setError("Failed to load projects."); });
    if (can("projects.assign_pm")) {
      getProjectManagers().then((result) => { if (!cancelled) setManagers(result); }).catch(() => {});
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const managersById = useMemo(() => Object.fromEntries(managers.map((m) => [m.id, m])), [managers]);
  const visible = (projects || []).filter((project) => project.name.toLowerCase().includes(query.toLowerCase()));

  function replaceProject(updated) {
    setProjects((current) => current.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
  }

  async function handleDelete() {
    setDeleteError("");
    try {
      await deleteProject(deleting.id);
      setProjects((current) => current.filter((p) => p.id !== deleting.id));
      setDeleting(null);
    } catch (err) {
      setDeleteError(err.response?.data?.detail || "Failed to delete project");
    }
  }

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Projects</h1>
            <p className="page-subtitle">Create projects and assign the project managers who can see their scores.</p>
          </div>
          {can("projects.create") && (
            <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>New project</button>
          )}
        </header>

        <input
          type="search" className="input" aria-label="Search projects" placeholder="Search projects…"
          value={query} onChange={(event) => setQuery(event.target.value)} style={{ maxWidth: 360 }}
        />

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {projects !== null && visible.length === 0 && (
          <div className="card" style={{ padding: 20 }}><p className="card-body">No projects found.</p></div>
        )}

        {visible.length > 0 && (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr><th>Project</th><th>Platforms</th><th>Project managers</th><th>Reviews</th><th>Created</th><th aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {visible.map((project) => (
                  <tr key={project.id}>
                    <td style={{ fontWeight: 600 }}>{project.name}</td>
                    <td>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {(project.platforms || []).length === 0 && <span style={{ color: "var(--color-text-muted)" }}>—</span>}
                        {(project.platforms || []).map((platform) => <span key={platform} className="tag tag-outline">{platform}</span>)}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {(project.manager_ids || []).length === 0 && <span style={{ color: "var(--color-text-muted)" }}>—</span>}
                        {(project.manager_ids || []).map((id) => (
                          <span key={id} className="tag tag-outline">{managersById[id] ? managerLabel(managersById[id]) : id}</span>
                        ))}
                      </div>
                    </td>
                    <td>{project.review_count}</td>
                    <td>{new Date(project.created_at).toLocaleDateString()}</td>
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      {can("projects.edit") && (
                        <button type="button" className="btn btn-ghost" aria-label={`Edit ${project.name}`} onClick={() => setRenaming(project)}>Edit</button>
                      )}
                      {can("projects.assign_pm") && (
                        <button type="button" className="btn btn-ghost" aria-label={`Assign PMs for ${project.name}`} onClick={() => setAssigning(project)}>Assign PMs</button>
                      )}
                      {can("projects.delete") && (
                        <button
                          type="button" className="btn btn-ghost" style={{ color: "var(--color-brand-coral)" }}
                          aria-label={`Delete ${project.name}`}
                          disabled={project.review_count > 0}
                          title={project.review_count > 0 ? `Has ${project.review_count} reviews — can't be deleted` : undefined}
                          onClick={() => { setDeleteError(""); setDeleting(project); }}
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {creating && (
        <ProjectDialog
          title="New project" initialName="" submitLabel="Create" withPlatforms
          onSubmit={async (name, platforms) => {
            const project = await createProject(name);
            const saved = platforms.length ? await setProjectPlatforms(project.id, platforms) : project;
            setProjects((current) => [{ ...project, ...saved }, ...(current || [])]);
          }}
          onClose={() => setCreating(false)}
        />
      )}
      {renaming && (
        <ProjectDialog
          title="Edit project" initialName={renaming.name} submitLabel="Save"
          withPlatforms initialPlatforms={renaming.platforms || []}
          onSubmit={async (name, platforms) => {
            const renamed = name !== renaming.name ? await updateProject(renaming.id, name) : {};
            const saved = await setProjectPlatforms(renaming.id, platforms);
            replaceProject({ ...renamed, ...saved, id: renaming.id });
          }}
          onClose={() => setRenaming(null)}
        />
      )}
      {assigning && (
        <AssignManagersDialog project={assigning} managers={managers} onSaved={replaceProject} onClose={() => setAssigning(null)} />
      )}
      {deleting && (
        <div className="dialog-backdrop" onClick={() => setDeleting(null)}>
          <div className="dialog" role="dialog" aria-label="Delete project" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">Delete {deleting.name}?</div>
            <div className="dialog-body">
              <p className="card-body">This permanently removes the project and its PM assignments.</p>
              {deleteError && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{deleteError}</p>}
            </div>
            <div className="dialog-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setDeleting(null)}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={handleDelete}>Delete project</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

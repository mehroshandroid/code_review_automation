import { useEffect, useState } from "react";
import TopNav from "../components/TopNav";
import { createProject, getProjects } from "../services/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProjects()
      .then((result) => { if (!cancelled) { setProjects(result); setLoaded(true); } })
      .catch(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    setError("");
    setCreating(true);
    try {
      const project = await createProject(name.trim());
      setProjects((current) => [project, ...current]);
      setName("");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "64px 24px 96px" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontWeight: "var(--font-heading-weight)", fontSize: 40, lineHeight: 1.1, letterSpacing: "-0.02em", margin: "0 0 12px" }}>
            Projects
          </h1>
          <p style={{ margin: 0, color: "var(--color-text-muted)", maxWidth: "60ch", fontSize: 16, lineHeight: 1.6 }}>
            Create a project to start tracking review history against it.
          </p>
        </header>

        <form onSubmit={handleCreate} className="card elev-md" style={{ padding: 28, marginBottom: "var(--space-5)" }}>
          <div className="card-title" style={{ fontSize: 18, marginBottom: "var(--space-3)" }}>New project</div>
          <div className="field">
            <label htmlFor="projectName">Project name</label>
            <input
              id="projectName"
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
            style={{ marginTop: "var(--space-4)" }}
            disabled={creating || !name.trim()}
          >
            Create
          </button>
        </form>

        {loaded && (
          <div className="card" style={{ padding: 20 }}>
            {projects.length === 0 ? (
              <p className="card-body">No projects yet -- create one above.</p>
            ) : (
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                {projects.map((project) => (
                  <div key={project.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--color-divider)" }}>
                    {project.name}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

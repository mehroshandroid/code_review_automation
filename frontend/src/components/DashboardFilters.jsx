import { useState } from "react";
import SearchableSelect from "./SearchableSelect";
import ProjectDialog from "./ProjectDialog";
import { PLATFORMS } from "../platforms";
import { createProject, updateProject } from "../services/api";

const ALL_PLATFORMS_OPTION = { value: null, label: "All platforms" };
const ALL_PROJECTS_OPTION = { value: null, label: "All projects" };

export default function DashboardFilters({
  year, years, onYearChange,
  platform, onPlatformChange,
  projectId, projects, onProjectChange, onProjectCreated, onProjectRenamed,
  onReset,
}) {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showRenameDialog, setShowRenameDialog] = useState(false);

  const yearOptions = years.map((y) => ({ value: y, label: String(y) }));
  const platformOptions = [ALL_PLATFORMS_OPTION, ...PLATFORMS.map((p) => ({ value: p.label, label: p.label }))];
  const projectOptions = [ALL_PROJECTS_OPTION, ...projects.map((p) => ({ value: p.id, label: p.name }))];
  const selectedProject = projects.find((p) => p.id === projectId);

  async function handleCreate(name) {
    const project = await createProject(name);
    onProjectCreated(project);
    onProjectChange(project.id);
  }

  async function handleRename(name) {
    const updated = await updateProject(selectedProject.id, name);
    onProjectRenamed(updated);
  }

  return (
    <div className="card" style={{ padding: 20, display: "flex", gap: "var(--space-3)", alignItems: "flex-end", flexWrap: "wrap" }}>
      <div className="field" style={{ minWidth: 140 }}>
        <label htmlFor="filterYear">Year</label>
        <SearchableSelect ariaLabel="Year" options={yearOptions} value={year} onChange={onYearChange} />
      </div>
      <div className="field" style={{ minWidth: 200 }}>
        <label htmlFor="filterPlatform">Platform</label>
        <SearchableSelect ariaLabel="Platform" options={platformOptions} value={platform} onChange={onPlatformChange} />
      </div>
      <div className="field" style={{ minWidth: 240, flex: 1 }}>
        <label htmlFor="filterProject">Project</label>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <div style={{ flex: 1 }}>
            <SearchableSelect
              ariaLabel="Project" options={projectOptions} value={projectId} onChange={onProjectChange}
              onAddNew={() => setShowCreateDialog(true)} addNewLabel="+ Add new project"
            />
          </div>
          {selectedProject && (
            <button
              type="button" className="btn btn-ghost" aria-label={`Rename ${selectedProject.name}`}
              style={{ flexShrink: 0 }}
              onClick={() => setShowRenameDialog(true)}
            >
              ✎
            </button>
          )}
        </div>
      </div>
      <button type="button" className="btn" onClick={onReset}>Reset filters</button>

      {showCreateDialog && (
        <ProjectDialog
          title="New project" initialName="" submitLabel="Create"
          onSubmit={handleCreate} onClose={() => setShowCreateDialog(false)}
        />
      )}

      {showRenameDialog && selectedProject && (
        <ProjectDialog
          title="Rename project" initialName={selectedProject.name} submitLabel="Save"
          onSubmit={handleRename} onClose={() => setShowRenameDialog(false)}
        />
      )}
    </div>
  );
}

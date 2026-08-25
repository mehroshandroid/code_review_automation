import { useRef, useState } from "react";
import SearchableSelect from "./SearchableSelect";
import ProjectDialog from "./ProjectDialog";
import { PLATFORMS } from "../platforms";
import { createProject, uploadCompletedReview } from "../services/api";

export default function UploadReviewDialog({ projects, onProjectCreated, onUploaded, onClose }) {
  const [projectId, setProjectId] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [pendingPlatform, setPendingPlatform] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [uploadedReview, setUploadedReview] = useState(null);
  const fileInputRef = useRef(null);

  const projectOptions = projects.map((p) => ({ value: p.id, label: p.name }));

  async function handleCreateProject(name) {
    const project = await createProject(name);
    onProjectCreated(project);
    setProjectId(project.id);
  }

  function handleSelectPlatform(platform) {
    if (!projectId || uploading) return;
    setError("");
    setPendingPlatform(platform);
    fileInputRef.current.click();
  }

  async function handleFileChange(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file || !pendingPlatform) return;
    setUploading(true);
    setError("");
    try {
      const review = await uploadCompletedReview({ projectId, platform: pendingPlatform.label, file });
      onUploaded(review);
      setUploadedReview(review);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to upload review.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="dialog-title">Upload a completed review</div>
        {uploadedReview ? (
          <div className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
            <p className="card-body" style={{ color: "#2E9E6B", fontWeight: 600 }}>
              ✓ Review uploaded successfully.
            </p>
            <p className="card-body" style={{ margin: 0 }}>
              {uploadedReview.project_name} · {uploadedReview.platform} · dated{" "}
              {new Date(uploadedReview.created_at).toLocaleDateString()}. The dashboard filters have been
              updated so you can see it below.
            </p>
          </div>
        ) : (
          <div className="dialog-body" style={{ display: "grid", gap: "var(--space-4)" }}>
            <div className="field">
              <label htmlFor="uploadReviewProject">Project</label>
              <SearchableSelect
                ariaLabel="Project" options={projectOptions} value={projectId} onChange={setProjectId}
                placeholder="Choose a project…" onAddNew={() => setShowCreateDialog(true)} addNewLabel="+ Add new project"
              />
            </div>

            <div className="field">
              <label>Platform</label>
              <p className="card-body" style={{ marginTop: 0 }}>
                Choose a platform, then pick the filled-in .xlsx review sheet to upload.
              </p>
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
                      cursor: projectId && !uploading ? "pointer" : "not-allowed",
                      opacity: projectId ? 1 : 0.5,
                    }}
                    onClick={() => handleSelectPlatform(platform)}
                  >
                    <div className="card-title" style={{ fontSize: 16 }}>
                      {platform.label}
                      {uploading && pendingPlatform?.id === platform.id ? " — uploading…" : ""}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

            <input
              ref={fileInputRef} type="file" accept=".xlsx" onChange={handleFileChange}
              style={{ display: "none" }} aria-label="Choose review sheet"
            />
          </div>
        )}
        <div className="dialog-actions">
          {uploadedReview ? (
            <button type="button" className="btn btn-primary" onClick={onClose}>Done</button>
          ) : (
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
          )}
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

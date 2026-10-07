import { useState } from "react";
import MultiSelect from "./MultiSelect";
import { setProjectManagers } from "../services/api";

export function managerLabel(manager) {
  return manager.name || manager.email;
}

export default function AssignManagersDialog({ project, managers, onSaved, onClose }) {
  const [values, setValues] = useState(project.manager_ids || []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      onSaved(await setProjectManagers(project.id, values));
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save project managers");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <div className="dialog-title">Assign project managers — {project.name}</div>
        <div className="dialog-body">
          {managers.length === 0 ? (
            <p className="card-body">No Project Manager accounts exist yet. An admin can create them on the Users page.</p>
          ) : (
            <div className="field">
              <label>Project managers</label>
              <MultiSelect
                ariaLabel="Project managers"
                options={managers.map((manager) => ({ value: manager.id, label: managerLabel(manager) }))}
                values={values}
                onChange={setValues}
                placeholder="Choose project managers…"
              />
            </div>
          )}
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}

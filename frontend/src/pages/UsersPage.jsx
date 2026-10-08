import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import { useAuth } from "../context/AuthContext";
import { ROLES, ROLE_LABELS } from "../permissions";
import { listUsers, createUser, updateUser, deleteUser, getProjects } from "../services/api";

function CreateUserDialog({ onSubmit, onClose }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("reviewer");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onSubmit(email, password, role, name);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create user.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">New user</div>
        <form onSubmit={handleSubmit} className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <div className="field">
            <label htmlFor="newUserName">Name</label>
            <input id="newUserName" type="text" className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="newUserEmail">Email</label>
            <input id="newUserEmail" type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="newUserPassword">Password</label>
            <input id="newUserPassword" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="newUserRole">Role</label>
            <select id="newUserRole" className="input" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
            </select>
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>Create</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SetPasswordDialog({ email, onSubmit, onClose }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onSubmit(password);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to set password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">Set a new password</div>
        <form onSubmit={handleSubmit} className="dialog-body" style={{ display: "grid", gap: "var(--space-3)" }}>
          <p className="card-body" style={{ margin: 0 }}>New password for {email}</p>
          <div className="field">
            <label htmlFor="newPassword">New password</label>
            <input id="newPassword" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [passwordDialogFor, setPasswordDialogFor] = useState(null);
  const [error, setError] = useState("");
  const [projectNames, setProjectNames] = useState({});

  function refresh() {
    return listUsers().then(setUsers);
  }

  useEffect(() => {
    refresh();
    getProjects()
      .then((projects) => setProjectNames(Object.fromEntries(projects.map((p) => [p.id, p.name]))))
      .catch(() => {});
  }, []);

  async function handleCreate(email, password, role, name) {
    await createUser(email, password, role, name);
    await refresh();
  }

  async function handleNameChange(userId, name) {
    setError("");
    try {
      const updated = await updateUser(userId, { name });
      setUsers((current) => current.map((u) => (u.id === userId ? { ...u, ...updated } : u)));
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update name.");
    }
  }

  async function handleRoleChange(userId, role) {
    setError("");
    try {
      await updateUser(userId, { role });
      await refresh();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to change role.");
    }
  }

  async function handleToggleActive(userId, isActive) {
    setError("");
    try {
      await updateUser(userId, { isActive });
      await refresh();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update status.");
    }
  }

  async function handleSetPassword(userId, password) {
    await updateUser(userId, { password });
    await refresh();
  }

  async function handleDelete(userId) {
    setError("");
    try {
      await deleteUser(userId);
      await refresh();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to delete user.");
    }
  }

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Users</h1>
            <p className="page-subtitle">Manage accounts and roles. Assign project managers to projects on the Projects page.</p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>Add user</button>
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {users && (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="table table--padded">
              <thead>
                <tr><th>Name</th><th>Email</th><th>Role</th><th>Projects</th><th>Status</th><th aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isSelf = currentUser && u.id === currentUser.id;
                  return (
                    <tr key={u.id}>
                      <td>
                        <input
                          aria-label={`Name for ${u.email}`} className="input" defaultValue={u.name || ""}
                          placeholder="—" style={{ minWidth: 140 }}
                          onBlur={(e) => {
                            if ((e.target.value.trim() || null) !== (u.name || null)) handleNameChange(u.id, e.target.value);
                          }}
                        />
                      </td>
                      <td>{u.email}</td>
                      <td>
                        <select
                          aria-label={`Role for ${u.email}`} className="input" value={u.role} disabled={isSelf}
                          onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        >
                          {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                        </select>
                      </td>
                      <td>
                        {u.role === "project_manager" && (u.project_ids || []).length > 0 ? (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {u.project_ids.map((id) => (
                              <Link key={id} to="/projects" className="tag tag-outline">{projectNames[id] || id}</Link>
                            ))}
                          </div>
                        ) : (
                          <span style={{ color: "var(--color-text-muted)" }}>—</span>
                        )}
                      </td>
                      <td>{u.is_active ? "Active" : "Deactivated"}</td>
                      <td style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end", whiteSpace: "nowrap" }}>
                        {!isSelf && (
                          u.is_active ? (
                            <button type="button" className="btn btn-ghost" aria-label={`Deactivate ${u.email}`} onClick={() => handleToggleActive(u.id, false)}>
                              Deactivate
                            </button>
                          ) : (
                            <button type="button" className="btn btn-ghost" aria-label={`Reactivate ${u.email}`} onClick={() => handleToggleActive(u.id, true)}>
                              Reactivate
                            </button>
                          )
                        )}
                        <button type="button" className="btn btn-ghost" aria-label={`Set password for ${u.email}`} onClick={() => setPasswordDialogFor(u)}>
                          Set password
                        </button>
                        {!isSelf && (
                          <button
                            type="button" className="btn btn-ghost" aria-label={`Delete ${u.email}`}
                            style={{ color: "var(--color-brand-coral)" }} onClick={() => handleDelete(u.id)}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {showCreate && <CreateUserDialog onSubmit={handleCreate} onClose={() => setShowCreate(false)} />}

      {passwordDialogFor && (
        <SetPasswordDialog
          email={passwordDialogFor.email}
          onSubmit={(password) => handleSetPassword(passwordDialogFor.id, password)}
          onClose={() => setPasswordDialogFor(null)}
        />
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import TopNav from "../components/TopNav";
import { listUsers, createUser, updateUser } from "../services/api";

const ROLES = ["admin", "reviewer", "user"];

function CreateUserDialog({ onSubmit, onClose }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onSubmit(email, password, role);
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
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
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

export default function UsersPage() {
  const [users, setUsers] = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  function refresh() {
    return listUsers().then(setUsers);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate(email, password, role) {
    await createUser(email, password, role);
    await refresh();
  }

  async function handleRoleChange(userId, role) {
    await updateUser(userId, { role });
    await refresh();
  }

  async function handleToggleActive(userId, isActive) {
    await updateUser(userId, { isActive });
    await refresh();
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <TopNav />
      <main style={{ maxWidth: 900, margin: "0 auto", padding: "40px 16px", display: "grid", gap: "var(--space-4)" }}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="card-title" style={{ fontSize: 20 }}>Users</div>
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>Add user</button>
        </header>

        {users && (
          <div className="card" style={{ padding: 20 }}>
            <table className="table">
              <thead>
                <tr><th>Email</th><th>Role</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>
                      <select
                        aria-label={`Role for ${u.email}`} className="input" value={u.role}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      >
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td>{u.is_active ? "Active" : "Deactivated"}</td>
                    <td>
                      {u.is_active ? (
                        <button type="button" className="btn btn-ghost" aria-label={`Deactivate ${u.email}`} onClick={() => handleToggleActive(u.id, false)}>
                          Deactivate
                        </button>
                      ) : (
                        <button type="button" className="btn btn-ghost" aria-label={`Reactivate ${u.email}`} onClick={() => handleToggleActive(u.id, true)}>
                          Reactivate
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

      {showCreate && <CreateUserDialog onSubmit={handleCreate} onClose={() => setShowCreate(false)} />}
    </div>
  );
}

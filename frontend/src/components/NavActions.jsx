import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { GearIcon } from "../icons";

export default function NavActions() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <>
      {(user.role === "admin" || user.role === "reviewer") && (
        <Link to="/settings" className="btn btn-ghost" aria-label="Settings"><GearIcon /></Link>
      )}
      {user.role === "admin" && (
        <Link to="/users" className="btn btn-ghost">Users</Link>
      )}
      <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{user.email} · {user.role}</span>
      <button type="button" className="btn btn-ghost" onClick={logout}>Log out</button>
    </>
  );
}

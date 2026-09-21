import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { GearIcon, UserIcon } from "../icons";

export default function NavActions() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!user) return null;

  return (
    <>
      {(user.role === "admin" || user.role === "reviewer") && (
        <Link to="/settings" className="btn btn-ghost" aria-label="Settings"><GearIcon /></Link>
      )}
      {user.role === "admin" && (
        <Link to="/users" className="btn btn-ghost">Users</Link>
      )}

      <div ref={containerRef} style={{ position: "relative" }}>
        <button
          type="button" className="btn btn-ghost" aria-label="User menu"
          style={{ borderRadius: 999, padding: 8 }} onClick={() => setOpen((current) => !current)}
        >
          <UserIcon />
        </button>
        {open && (
          <div
            className="card elev-md"
            style={{ position: "absolute", top: "calc(100% + 4px)", right: 0, zIndex: 50, padding: 16, minWidth: 220 }}
          >
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600, wordBreak: "break-all" }}>{user.email}</p>
            <p style={{ margin: "2px 0 12px", fontSize: 12, color: "var(--color-text-muted)", textTransform: "capitalize" }}>{user.role}</p>
            <button type="button" className="btn btn-block" onClick={logout}>Log out</button>
          </div>
        )}
      </div>
    </>
  );
}

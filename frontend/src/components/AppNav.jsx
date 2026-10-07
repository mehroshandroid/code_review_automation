import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { hasAny, hasPermission, initialsFor, ROLE_LABELS } from "../permissions";

const LINKS = [
  { to: "/", label: "Dashboard", anyOf: ["dashboard.view_all", "dashboard.view_assigned"], end: true },
  { to: "/my-reviews", label: "My reviews", anyOf: ["my_reviews.view"] },
  { to: "/projects", label: "Projects", anyOf: ["projects.view"] },
  { to: "/users", label: "Users", anyOf: ["users.manage"] },
];

export default function AppNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false);
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  if (!user) return null;

  const displayName = user.name || user.email;
  const menuItems = [
    hasPermission(user, "settings.manage") && { label: "Settings", to: "/settings" },
    hasPermission(user, "users.manage") && { label: "Users", to: "/users" },
  ].filter(Boolean);

  function go(to) {
    setOpen(false);
    navigate(to);
  }

  return (
    <nav className="app-nav" aria-label="Main">
      <Link to={user.home_path || "/"} className="app-nav-brand">
        <span className="logo-mark" aria-hidden="true">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="nav-brand">CodeAssure</span>
      </Link>

      <div className="app-nav-links">
        {LINKS.filter((link) => hasAny(user, link.anyOf)).map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end} className="app-nav-link">
            {link.label}
          </NavLink>
        ))}
      </div>

      <div ref={containerRef} className="app-nav-account">
        <button
          ref={triggerRef}
          type="button"
          className="app-nav-account-trigger"
          aria-label="Account menu"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          <span className="avatar" aria-hidden="true">{initialsFor(user)}</span>
          <span className="app-nav-account-text">
            <span className="app-nav-account-name">{displayName}</span>
            <span className="app-nav-account-role">{ROLE_LABELS[user.role] || user.role}</span>
          </span>
          <span aria-hidden="true" className="app-nav-caret">▾</span>
        </button>
        {open && (
          <div role="menu" className="card elev-md app-nav-menu">
            <div className="app-nav-menu-header">
              <div className="app-nav-account-name">{displayName}</div>
              <div className="app-nav-account-role">{user.email}</div>
            </div>
            {menuItems.map((item) => (
              <button key={item.to} type="button" role="menuitem" className="app-nav-menu-item" onClick={() => go(item.to)}>
                {item.label}
              </button>
            ))}
            <div className="app-nav-menu-divider" role="separator" />
            <button type="button" role="menuitem" className="app-nav-menu-item" onClick={() => { setOpen(false); logout(); }}>
              Log out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

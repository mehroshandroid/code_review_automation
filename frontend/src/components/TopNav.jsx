import { Link } from "react-router-dom";
import NavActions from "./NavActions";

export default function TopNav() {
  return (
    <nav className="nav">
      <Link to="/" style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", textDecoration: "none", color: "inherit" }}>
        <span className="logo-mark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="nav-brand">Code Review Automation</span>
      </Link>
      <div style={{ marginLeft: "auto", display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
        <NavActions />
      </div>
      <Link to="/" className="btn btn-ghost">← Home</Link>
    </nav>
  );
}

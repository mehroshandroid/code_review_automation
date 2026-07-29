import { Link } from "react-router-dom";

export default function TopNav() {
  return (
    <nav className="nav">
      <Link to="/" className="nav-brand" style={{ textDecoration: "none", color: "inherit" }}>
        Code Review Automation
      </Link>
      <Link to="/" className="btn btn-ghost" style={{ marginLeft: "auto" }}>← Home</Link>
    </nav>
  );
}

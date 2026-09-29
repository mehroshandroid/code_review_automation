import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getMicrosoftLoginUrl } from "../services/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const ssoFailed = searchParams.get("error") === "sso_failed";

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "var(--color-bg)" }}>
      <form onSubmit={handleSubmit} className="card elev-sm" style={{ padding: 32, width: 360, display: "grid", gap: "var(--space-4)" }}>
        <div className="card-title" style={{ fontSize: 20 }}>Log in</div>
        <a href={getMicrosoftLoginUrl()} className="btn" style={{ textAlign: "center" }}>
          Sign in with Microsoft
        </a>
        {ssoFailed && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>Microsoft sign-in failed. Please try again.</p>}
        <div style={{ borderTop: "1px solid var(--color-divider)" }} />
        <div className="field">
          <label htmlFor="loginEmail">Email</label>
          <input
            id="loginEmail" type="email" className="input" value={email}
            onChange={(event) => setEmail(event.target.value)} required
          />
        </div>
        <div className="field">
          <label htmlFor="loginPassword">Password</label>
          <input
            id="loginPassword" type="password" className="input" value={password}
            onChange={(event) => setPassword(event.target.value)} required
          />
        </div>
        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
    </div>
  );
}

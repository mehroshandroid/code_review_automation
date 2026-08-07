import TopNav from "../components/TopNav";
import UploadForm from "../components/UploadForm";

export default function PlaceholderReviewFlow({ platform }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "64px 24px 96px" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontWeight: "var(--font-heading-weight)", fontSize: 40, lineHeight: 1.1, letterSpacing: "-0.02em", margin: "0 0 12px" }}>
            {platform.label} Code Review Automation
          </h1>
        </header>

        <div className="card elev-md" style={{ padding: 32, marginBottom: "var(--space-5)" }}>
          <div className="card-kicker">Coming soon</div>
          <div className="card-title" style={{ fontSize: 22 }}>{platform.label} support is on the way</div>
          <p className="card-body">
            The review flow will work the same way as Android once {platform.label} support ships.
          </p>
        </div>

        <UploadForm onSubmit={() => {}} disabled disabledLabel="Coming soon" />
      </main>
    </div>
  );
}

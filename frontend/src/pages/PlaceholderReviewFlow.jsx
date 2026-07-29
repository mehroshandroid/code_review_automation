import TopNav from "../components/TopNav";
import UploadForm from "../components/UploadForm";
import CornerMarks from "../components/CornerMarks";

export default function PlaceholderReviewFlow({ platform }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            {platform.label} Code Review Automation
          </h1>
        </header>

        <div className="card blueprint elev-md" style={{ padding: "var(--space-6)", marginBottom: "var(--space-5)" }}>
          <CornerMarks />
          <div className="card-kicker">Coming soon</div>
          <div className="card-title" style={{ fontSize: 20 }}>{platform.label} support is on the way</div>
          <p className="card-body">
            The review flow will work the same way as Android once {platform.label} support ships.
          </p>
        </div>

        <UploadForm onSubmit={() => {}} disabled disabledLabel="Coming soon" />
      </main>
    </div>
  );
}

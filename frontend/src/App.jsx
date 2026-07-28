import { useCallback, useState } from "react";
import UploadForm from "./components/UploadForm";
import ProgressTracker from "./components/ProgressTracker";
import FindingsPanel from "./components/FindingsPanel";
import CategoryScoresChart from "./components/CategoryScoresChart";
import StatsDisplay from "./components/StatsDisplay";
import CornerMarks from "./components/CornerMarks";
import { createReview } from "./services/api";

export default function App() {
  const [state, setState] = useState("idle"); // idle | uploading | polling | completed | error
  const [reviewId, setReviewId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  const handleUpload = useCallback(async (androidZip, excelTemplate) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const result = await createReview(androidZip, excelTemplate);
      if (result.status === "error") {
        setErrorMessage(result.error || "Upload failed");
        setState("error");
        return;
      }
      setReviewId(result.review_id);
      setState("polling");
    } catch (err) {
      setErrorMessage("Failed to start review. Is the server running?");
      setState("error");
    }
  }, []);

  const handleProgressUpdate = useCallback((data) => {
    setProgressData(data);
    if (data.status === "completed") {
      setState("completed");
    } else if (data.status === "error") {
      setErrorMessage(data.error || "Review failed");
      setState("error");
    }
  }, []);

  function handleReset() {
    setState("idle");
    setReviewId(null);
    setProgressData(null);
    setErrorMessage("");
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav"><span className="nav-brand">Code Review Automation</span></nav>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            Android Code Review Automation
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Upload an Android project and a scoring template. The reviewer analyzes structure, security, tests and
            dependency versions, scores each category with AI, and hands back a populated workbook.
          </p>
        </header>

        {(state === "idle" || state === "uploading") && (
          <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} />
        )}

        {state === "polling" && reviewId && (
          <>
            <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
            {progressData && ["scoring", "generating"].includes(progressData.phase) && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <CategoryScoresChart categoryScores={progressData.category_scores} />
              </div>
            )}
            {progressData && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <FindingsPanel
                  warnings={progressData.warnings}
                  testCoverage={progressData.test_coverage}
                  secretsFound={progressData.secrets_found}
                />
              </div>
            )}
          </>
        )}

        {state === "completed" && progressData && (
          <StatsDisplay
            totalScorePct={progressData.total_score_pct}
            warnings={progressData.warnings}
            testCoverage={progressData.test_coverage}
            secretsFound={progressData.secrets_found}
            categoryScores={progressData.category_scores}
            stats={progressData.stats}
            downloadUrl={progressData.download_url}
            onReset={handleReset}
          />
        )}

        {state === "error" && (
          <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
            <CornerMarks />
            <div className="card-kicker">Error</div>
            <div className="card-title" style={{ fontSize: 20 }}>Review failed</div>
            <p className="card-body">{errorMessage}</p>
            <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
              <button type="button" className="btn btn-primary blueprint" onClick={handleReset}>
                <CornerMarks />
                Try again
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

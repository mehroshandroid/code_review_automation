import { useCallback, useState } from "react";
import UploadForm from "../components/UploadForm";
import ProgressTracker from "../components/ProgressTracker";
import FindingsPanel from "../components/FindingsPanel";
import CategoryScoresChart from "../components/CategoryScoresChart";
import LlmUsageStats from "../components/LlmUsageStats";
import PromptDebugLog from "../components/PromptDebugLog";
import ReportTable from "../components/ReportTable";
import StatsDisplay from "../components/StatsDisplay";
import ReviewMetaBar from "../components/ReviewMetaBar";
import CornerMarks from "../components/CornerMarks";
import TopNav from "../components/TopNav";
import { createReview, getOllamaModels } from "../services/api";
import { getLlmProvider, getOllamaModel } from "../services/llmProviderStorage";
import { getCompileCheckMode } from "../services/compileCheckModeStorage";

const SCORING_PHASES = ["scoring", "generating", "completed"];

export default function AndroidReviewFlow({ platform = { id: "android", label: "Android" } }) {
  const [state, setState] = useState("idle"); // idle | uploading | polling | completed | error
  const [reviewId, setReviewId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [bottomView, setBottomView] = useState("report"); // report | debug
  const [reviewMeta, setReviewMeta] = useState(null); // { llmProvider, llmModel, source, compileCheckMode }

  const handleUpload = useCallback(async ({ androidZip, excelTemplate, devopsRepoUrl, devopsPat, devopsBranch }) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const models = await getOllamaModels().catch(() => []);
      const storedProvider = getLlmProvider();
      const effectiveProvider = storedProvider === "ollama" && models.length === 0 ? "azure" : storedProvider;
      const effectiveModel = effectiveProvider === "ollama" ? getOllamaModel() : null;
      const compileCheckMode = getCompileCheckMode();
      setReviewMeta({
        llmProvider: effectiveProvider,
        llmModel: effectiveModel,
        source: devopsRepoUrl ? "devops" : "upload",
        compileCheckMode,
      });

      const result = await createReview(
        androidZip, excelTemplate, effectiveProvider, effectiveModel, compileCheckMode, platform.label,
        devopsRepoUrl, devopsPat, devopsBranch
      );
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
    setReviewMeta(null);
  }

  const isRunningOrDone = state === "polling" || state === "completed";
  const showLlmDetails = !!progressData && SCORING_PHASES.includes(progressData.phase);

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: isRunningOrDone ? 1440 : 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-3)", flexWrap: "wrap", marginBottom: "var(--space-2)" }}>
            <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: 0 }}>
              {progressData?.project_name || `${platform.label} Code Review Automation`}
            </h1>
            {reviewMeta && (
              <ReviewMetaBar
                llmProvider={reviewMeta.llmProvider}
                llmModel={reviewMeta.llmModel}
                source={reviewMeta.source}
                compileCheckMode={reviewMeta.compileCheckMode}
              />
            )}
          </div>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Upload your {platform.label} project and a scoring template. The reviewer analyzes structure, security,
            tests and dependency versions, scores each category with AI, and hands back a populated workbook.
          </p>
        </header>

        {(state === "idle" || state === "uploading") && (
          <UploadForm
            onSubmit={handleUpload}
            disabled={state === "uploading"}
            showCompileCheckToggle
            platformLabel={platform.label}
          />
        )}

        {isRunningOrDone && reviewId && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
              <div>
                {state === "polling" && (
                  <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
                )}
                {progressData && (
                  <div style={{ marginTop: state === "polling" ? "var(--space-5)" : 0 }}>
                    <FindingsPanel
                      warnings={progressData.warnings}
                      testCoverage={progressData.test_coverage}
                      secretsFound={progressData.secrets_found}
                      lintIssues={progressData.lint_issues}
                      compileStatus={progressData.compile_status}
                    />
                  </div>
                )}
                {state === "completed" && progressData && (
                  <div style={{ marginTop: "var(--space-5)" }}>
                    <StatsDisplay
                      totalScorePct={progressData.total_score_pct}
                      warnings={progressData.warnings}
                      secretsFound={progressData.secrets_found}
                      lintIssues={progressData.lint_issues}
                      stats={progressData.stats}
                      downloadUrl={progressData.download_url}
                      onReset={handleReset}
                    />
                  </div>
                )}
              </div>

              <div>
                {showLlmDetails && (
                  <>
                    <CategoryScoresChart categoryScores={progressData.category_scores} />
                    <div style={{ marginTop: "var(--space-4)" }}>
                      <LlmUsageStats promptLog={progressData.prompt_log} />
                    </div>
                  </>
                )}
              </div>
            </div>

            {showLlmDetails && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
                  <button
                    type="button"
                    className={`btn ${bottomView === "report" ? "btn-primary" : ""}`}
                    onClick={() => setBottomView("report")}
                  >
                    Report
                  </button>
                  <button
                    type="button"
                    className={`btn ${bottomView === "debug" ? "btn-primary" : ""}`}
                    onClick={() => setBottomView("debug")}
                  >
                    Debug info
                  </button>
                </div>
                {bottomView === "report" ? (
                  <ReportTable categoryScores={progressData.category_scores} />
                ) : (
                  <PromptDebugLog codeContext={progressData.code_context} promptLog={progressData.prompt_log} />
                )}
              </div>
            )}
          </>
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

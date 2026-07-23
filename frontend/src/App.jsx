import { useCallback, useState } from "react";
import UploadForm from "./components/UploadForm";
import ProgressTracker from "./components/ProgressTracker";
import FindingsPanel from "./components/FindingsPanel";
import StatsDisplay from "./components/StatsDisplay";
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
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">Android Code Review Automation</h1>

      {(state === "idle" || state === "uploading") && (
        <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} />
      )}

      {state === "polling" && reviewId && (
        <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
      )}

      {progressData && (state === "polling" || state === "completed") && (
        <FindingsPanel
          warnings={progressData.warnings}
          testCoverage={progressData.test_coverage}
          secretsFound={progressData.secrets_found}
        />
      )}

      {state === "completed" && progressData && (
        <StatsDisplay stats={progressData.stats} downloadUrl={progressData.download_url} />
      )}

      {state === "error" && (
        <div className="space-y-3">
          <p className="text-red-600">{errorMessage}</p>
        </div>
      )}

      {(state === "completed" || state === "error") && (
        <button onClick={handleReset} className="text-blue-600 underline">
          Start New Review
        </button>
      )}
    </div>
  );
}

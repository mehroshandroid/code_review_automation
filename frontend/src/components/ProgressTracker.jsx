import { useEffect, useState } from "react";
import { getProgress } from "../services/api";
import { CheckCircleIcon, SpinnerIcon, CircleIcon } from "../icons";

const POLL_INTERVAL_MS = 2000;

const BASE_STEPS = [
  { phase: "extracting", label: "Extracting archive" },
  { phase: "analyzing", label: "Analyzing code" },
  { phase: "compiling", label: "Compiling & linting" },
  { phase: "scoring", label: "Scoring with AI" },
  { phase: "generating", label: "Generating report" },
];

const FETCHING_STEP = { phase: "fetching", label: "Downloading code from repository" };

function stepIndexForPhase(steps, phase) {
  if (phase === "completed" || phase === "error") return steps.length;
  return steps.findIndex((step) => step.phase === phase);
}

export default function ProgressTracker({ reviewId, onUpdate }) {
  const [progressData, setProgressData] = useState(null);

  useEffect(() => {
    let intervalId;
    let cancelled = false;

    async function poll() {
      const data = await getProgress(reviewId);
      if (cancelled) return;
      setProgressData(data);
      onUpdate(data);
      if (data.status !== "processing") {
        clearInterval(intervalId);
      }
    }

    poll();
    intervalId = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [reviewId, onUpdate]);

  const phase = progressData?.phase ?? "pending";
  const message = progressData?.message ?? "";
  const steps = progressData?.source === "devops" ? [FETCHING_STEP, ...BASE_STEPS] : BASE_STEPS;
  const currentIndex = stepIndexForPhase(steps, phase);

  return (
    <div className="card elev-md" style={{ padding: 32 }}>
      <div className="card-kicker">Step 2 of 2</div>
      <div className="card-title" style={{ fontSize: 22 }}>Reviewing your project</div>
      <div style={{ display: "grid", gap: 4, marginTop: "var(--space-5)" }}>
        {steps.map((step, index) => {
          const done = currentIndex > index || currentIndex === steps.length;
          const active = index === currentIndex;
          return (
            <div key={step.phase} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", padding: "10px 0" }}>
              {done && <CheckCircleIcon />}
              {active && <SpinnerIcon />}
              {!done && !active && <CircleIcon />}
              <div>
                <span style={{ fontSize: 15, color: done || active ? "var(--color-text)" : "var(--color-dashed-border)" }}>{step.label}</span>
                {active && message && (
                  <p className="text-muted" style={{ margin: 0, fontSize: 12 }}>{message}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { getProgress } from "../services/api";
import CornerMarks from "./CornerMarks";
import { CheckCircleIcon, SpinnerIcon, CircleIcon } from "../icons";

const POLL_INTERVAL_MS = 2000;

const STEPS = [
  { phase: "extracting", label: "Extracting archive" },
  { phase: "analyzing", label: "Analyzing code" },
  { phase: "compiling", label: "Compiling & linting" },
  { phase: "scoring", label: "Scoring with AI" },
  { phase: "generating", label: "Generating report" },
];

function stepIndexForPhase(phase) {
  if (phase === "completed" || phase === "error") return STEPS.length;
  return STEPS.findIndex((step) => step.phase === phase);
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
  const currentIndex = stepIndexForPhase(phase);

  return (
    <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
      <CornerMarks />
      <div className="card-kicker">Step 2 of 2</div>
      <div className="card-title" style={{ fontSize: 20 }}>Reviewing your project</div>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-5)" }}>
        {STEPS.map((step, index) => {
          const done = currentIndex > index || currentIndex === STEPS.length;
          const active = index === currentIndex;
          return (
            <div key={step.phase} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", padding: "var(--space-2) 0" }}>
              {done && <CheckCircleIcon />}
              {active && <SpinnerIcon />}
              {!done && !active && <CircleIcon />}
              <div>
                <span style={{ opacity: done || active ? 1 : 0.5 }}>{step.label}</span>
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

export function formatStageTime(iso) {
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function relativeTime(iso, now = Date.now()) {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function stagesFor(assignment, initiatedAt) {
  const ai = assignment.run_status === "completed" ? "done" : assignment.run_status === "failed" ? "failed" : "pending";
  return [
    { key: "initiated", label: "Initiated", state: initiatedAt ? "done" : "pending", at: initiatedAt || null },
    { key: "url", label: "URL added", state: assignment.url_submitted_at ? "done" : "pending", at: assignment.url_submitted_at || null },
    { key: "ai", label: "AI review done", state: ai, at: ai === "pending" ? null : assignment.finished_at || null },
    {
      key: "feedback", label: "Reviewer feedback",
      state: assignment.review_status === "approved" ? "done" : "pending", at: assignment.review_approved_at || null,
    },
  ];
}

function describeStage(stage) {
  if (stage.state === "pending") return `${stage.label} — pending`;
  const when = stage.at ? ` ${formatStageTime(stage.at)}` : "";
  return `${stage.label} — ${stage.state}${when}`;
}

export function StageDots({ assignment, initiatedAt }) {
  const stages = stagesFor(assignment, initiatedAt);
  return (
    <span className="stage-dots" role="img" aria-label={stages.map(describeStage).join("; ")}>
      {stages.map((stage) => (
        <span key={stage.key} className={`stage-dot stage-dot--${stage.state}`} title={describeStage(stage)} />
      ))}
    </span>
  );
}

export function StageTimeline({ assignment, initiatedAt }) {
  return (
    <ol className="stage-timeline">
      {stagesFor(assignment, initiatedAt).map((stage) => (
        <li key={stage.key} className={`stage stage--${stage.state}`}>
          <span className={`stage-dot stage-dot--${stage.state}`} aria-hidden="true" />
          <span className="stage-label">{stage.label}</span>
          <span className="stage-time">
            {stage.state === "pending" ? "Pending" : stage.at ? formatStageTime(stage.at) : stage.state === "failed" ? "Failed" : "Done"}
          </span>
        </li>
      ))}
    </ol>
  );
}

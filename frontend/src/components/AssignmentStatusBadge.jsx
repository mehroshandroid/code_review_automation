const PHASE_LABELS = {
  fetching: "Fetching", extracting: "Extracting", analyzing: "Analyzing", compiling: "Compiling",
  scoring: "Scoring", generating: "Generating", completed: "Finishing",
};

export function assignmentStatusLabel(assignment) {
  switch (assignment.run_status) {
    case "waiting_for_url": return "Waiting for URL";
    case "queued": return assignment.queue_position ? `Queued · #${assignment.queue_position}` : "Queued";
    case "running": {
      const phase = PHASE_LABELS[assignment.run_phase] || "Starting";
      return `Running · ${phase}${assignment.run_progress != null ? ` ${assignment.run_progress}%` : ""}`;
    }
    case "completed": return assignment.review_status === "approved" ? "Approved" : "Completed";
    case "failed": return "Failed";
    default: return assignment.run_status;
  }
}

export default function AssignmentStatusBadge({ assignment }) {
  return <span className={`run-badge run-badge--${assignment.run_status.replace(/_/g, "-")}`}>{assignmentStatusLabel(assignment)}</span>;
}

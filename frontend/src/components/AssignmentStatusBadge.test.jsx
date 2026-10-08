import { assignmentStatusLabel } from "./AssignmentStatusBadge";

test.each([
  [{ run_status: "waiting_for_url" }, "Waiting for URL"],
  [{ run_status: "queued", queue_position: 2 }, "Queued · #2"],
  [{ run_status: "queued", queue_position: null }, "Queued"],
  [{ run_status: "running", run_phase: "scoring", run_progress: 70 }, "Running · Scoring 70%"],
  [{ run_status: "running", run_phase: null, run_progress: null }, "Running · Starting"],
  [{ run_status: "completed", review_status: "pending_approval" }, "Completed"],
  [{ run_status: "completed", review_status: "approved" }, "Approved"],
  [{ run_status: "failed" }, "Failed"],
])("%o → %s", (assignment, label) => {
  expect(assignmentStatusLabel(assignment)).toBe(label);
});

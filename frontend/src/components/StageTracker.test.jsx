import { render, screen } from "@testing-library/react";
import { relativeTime, StageDots, StageTimeline, stagesFor } from "./StageTracker";

const INIT = "2026-10-07T09:00:00Z";
const base = { run_status: "waiting_for_url", url_submitted_at: null, finished_at: null, review_status: null, review_approved_at: null };

test("waiting for URL: only initiated is done", () => {
  expect(stagesFor(base, INIT).map((s) => s.state)).toEqual(["done", "pending", "pending", "pending"]);
});

test("queued after URL", () => {
  expect(stagesFor({ ...base, run_status: "queued", url_submitted_at: INIT }, INIT).map((s) => s.state)).toEqual(["done", "done", "pending", "pending"]);
});

test("failed AI run", () => {
  const stages = stagesFor({ ...base, run_status: "failed", url_submitted_at: INIT, finished_at: INIT }, INIT);
  expect(stages[2]).toMatchObject({ state: "failed", at: INIT });
});

test("completed and approved", () => {
  const a = { ...base, run_status: "completed", url_submitted_at: INIT, finished_at: INIT, review_status: "approved", review_approved_at: INIT };
  expect(stagesFor(a, INIT).map((s) => s.state)).toEqual(["done", "done", "done", "done"]);
});

test("dots carry titles and an accessible summary", () => {
  render(<StageDots assignment={{ ...base, run_status: "queued", url_submitted_at: INIT }} initiatedAt={INIT} />);
  const group = screen.getByRole("img");
  expect(group.getAttribute("aria-label")).toMatch(/^Initiated — done .*; URL added — done .*; AI review done — pending; Reviewer feedback — pending$/);
  expect(group.querySelectorAll(".stage-dot--done")).toHaveLength(2);
});

test("timeline lists labels", () => {
  render(<StageTimeline assignment={base} initiatedAt={INIT} />);
  expect(screen.getByText("Reviewer feedback")).toBeInTheDocument();
  expect(screen.getAllByText("Pending")).toHaveLength(3);
});

test("relative time", () => {
  const now = new Date("2026-10-08T12:00:00Z").getTime();
  expect(relativeTime("2026-10-08T11:59:30Z", now)).toBe("just now");
  expect(relativeTime("2026-10-08T11:15:00Z", now)).toBe("45m ago");
  expect(relativeTime("2026-10-08T09:00:00Z", now)).toBe("3h ago");
  expect(relativeTime("2026-10-06T12:00:00Z", now)).toBe("2d ago");
});

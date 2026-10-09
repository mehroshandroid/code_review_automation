import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuarterCard from "./QuarterCard";

const base = {
  quarter: 3, start: "2026-07-01", end: "2026-09-30", status: "overdue",
  covered: [{ platform: "Android", review_id: "a3", reviewed_at: "2026-08-01T00:00:00Z" }],
  missing: ["iOS"], can_initiate: true, cycle: null,
};

test.each([
  ["done", "Done"], ["in_progress", "In progress"], ["overdue", "Overdue"],
  ["not_started", "Not started"], ["not_applicable", "N/A"],
])("%s card shows its badge and tint class", (status, label) => {
  const { container } = render(<QuarterCard entry={{ ...base, status }} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.getByText(label)).toBeInTheDocument();
  expect(container.firstChild).toHaveClass(`quarter-card--${status.replace("_", "-")}`);
});

test("lists covered and missing platforms with the quarter label", () => {
  render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.getByText("Q3 · Jul–Sep")).toBeInTheDocument();
  expect(screen.getByText(/Android/).closest("li")).toHaveTextContent("✓");
  expect(screen.getByText(/iOS/).closest("li")).toHaveTextContent("○");
});

test("shows cycle info", () => {
  const entry = { ...base, can_initiate: false, cycle: {
    id: "c1", initiated_at: "2026-10-02T10:00:00Z", initiated_by_name: "Cora",
    assignments: [{ platform: "Android", reviewer_id: "r", reviewer_name: "Rae" }],
  } };
  render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate onInitiate={jest.fn()} />);
  expect(screen.getByText(/Initiated .* by Cora/)).toBeInTheDocument();
  expect(screen.getByText(/Rae/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /initiate review/i })).not.toBeInTheDocument();
});

test("Initiate button only when allowed by entry and permission", async () => {
  const user = userEvent.setup();
  const onInitiate = jest.fn();
  const { rerender } = render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate onInitiate={onInitiate} />);
  await user.click(screen.getByRole("button", { name: /initiate review/i }));
  expect(onInitiate).toHaveBeenCalled();
  rerender(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={onInitiate} />);
  expect(screen.queryByRole("button", { name: /initiate review/i })).not.toBeInTheDocument();
});

test("a late in-progress quarter shows a Late marker", () => {
  render(<QuarterCard entry={{ ...base, status: "in_progress", late: true }} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.getByText("In progress")).toBeInTheDocument();
  expect(screen.getByText("Late")).toBeInTheDocument();
});

test("an on-time in-progress quarter has no Late marker", () => {
  render(<QuarterCard entry={{ ...base, status: "in_progress", late: false }} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.queryByText("Late")).not.toBeInTheDocument();
});

test("Manage button and run status lines for an initiated quarter", async () => {
  const user = userEvent.setup();
  const onManage = jest.fn();
  const entry = { ...base, status: "in_progress", covered: [], missing: ["Android", "iOS"], can_initiate: false, cycle: {
    id: "c1", initiated_at: "2026-10-02T10:00:00Z", initiated_by_name: "Cora", assignments: [
      { platform: "Android", reviewer_id: "r", reviewer_name: "Rae", run_status: "running", run_phase: "scoring", run_progress: 50 },
      { platform: "iOS", reviewer_id: "r", reviewer_name: "Rae", run_status: "failed" },
    ] } };
  render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate canManage onManage={onManage} onInitiate={jest.fn()} />);
  expect(screen.getByText(/Running · Scoring 50%/)).toBeInTheDocument();
  expect(screen.getByText(/Failed/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Manage" }));
  expect(onManage).toHaveBeenCalled();
});

test("no Manage button without a cycle or permission", () => {
  render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} canManage onManage={jest.fn()} onInitiate={jest.fn()} />);
  expect(screen.queryByRole("button", { name: "Manage" })).not.toBeInTheDocument();
});

test("stage dots appear per platform once a cycle exists", () => {
  const entry = { ...base, status: "in_progress", covered: [], missing: ["Android", "iOS"], can_initiate: false, cycle: {
    id: "c1", initiated_at: "2026-10-02T10:00:00Z", initiated_by_name: "Cora", assignments: [
      { platform: "Android", reviewer_id: "r", reviewer_name: "Rae", run_status: "waiting_for_url" },
      { platform: "iOS", reviewer_id: "r", reviewer_name: "Rae", run_status: "queued", url_submitted_at: "2026-10-03T10:00:00Z" },
    ] } };
  const { container } = render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(container.querySelectorAll(".stage-dots")).toHaveLength(2);
});

test("no stage dots without a cycle", () => {
  const { container } = render(<QuarterCard entry={base} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(container.querySelectorAll(".stage-dots")).toHaveLength(0);
});

test("a platform reviewed after the quarter ended is marked late", () => {
  const entry = { ...base, status: "done", late: true, missing: [], covered: [
    { platform: "Android", review_id: "a3", reviewed_at: "2026-08-01T00:00:00Z", late: false },
    { platform: "iOS", review_id: "i3", reviewed_at: "2026-10-08T00:00:00Z", late: true },
  ] };
  render(<QuarterCard entry={entry} platforms={["Android", "iOS"]} canInitiate={false} onInitiate={jest.fn()} />);
  expect(screen.getByText(/iOS/).closest("li")).toHaveTextContent("(late)");
  expect(screen.getByText(/Android/).closest("li")).not.toHaveTextContent("(late)");
  expect(screen.getByText("Late")).toBeInTheDocument();
});

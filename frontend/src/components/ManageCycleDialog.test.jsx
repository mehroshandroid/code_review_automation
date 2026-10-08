import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ManageCycleDialog from "./ManageCycleDialog";
import { getReviewers, changeAssignmentReviewer, retryAssignment, rerunAssignment } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getReviewers: jest.fn(), changeAssignmentReviewer: jest.fn(), retryAssignment: jest.fn(), rerunAssignment: jest.fn(),
}));

const a = (platform, extra) => ({ platform, reviewer_id: "r1", reviewer_name: "Rae", devops_url: "https://dev.azure.com/o/p/_git/x",
  devops_branch: null, run_phase: null, run_progress: null, run_error: null, failure_kind: null, review_id: null,
  review_status: null, attempts: 1, queue_position: null, ...extra });
const entry = { quarter: 4, cycle: { id: "c1", initiated_at: "2026-10-07T00:00:00Z", initiated_by_name: "Cora", assignments: [
  a("Android", { run_status: "completed", review_id: "rv1", review_status: "pending_approval" }),
  a("iOS", { run_status: "failed", run_error: "Could not reach Azure DevOps." }),
  a(".NET", { run_status: "completed", review_id: "rv2", review_status: "approved" }),
] } };

beforeEach(() => {
  jest.resetAllMocks();
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }, { id: "r2", email: "sam@example.com", name: "Sam" }]);
});

function renderDialog(onChanged = jest.fn()) {
  render(<ManageCycleDialog project={{ id: "p1", name: "Moove" }} year={2026} entry={entry} onChanged={onChanged} onClose={jest.fn()} />);
  return onChanged;
}

function row(platform) {
  return screen.getByRole("row", { name: new RegExp(`^${platform.replace(".", "\\.")}`) });
}

test("lists platforms with status, error and reviewer", async () => {
  renderDialog();
  expect(screen.getByText("Q4 2026 review — Moove")).toBeInTheDocument();
  await screen.findAllByRole("option", { name: "Sam" });
  expect(within(row("iOS")).getByText("Failed")).toBeInTheDocument();
  expect(within(row("iOS")).getByText("Could not reach Azure DevOps.")).toBeInTheDocument();
  expect(within(row(".NET")).getByLabelText("Reviewer for .NET")).toBeDisabled();
  expect(within(row(".NET")).queryByRole("button", { name: "Re-run" })).not.toBeInTheDocument();
});

test("changing the reviewer saves and reports the change", async () => {
  const user = userEvent.setup();
  changeAssignmentReviewer.mockResolvedValue(a("Android", { run_status: "completed", review_id: "rv1", reviewer_id: "r2", reviewer_name: "Sam" }));
  const onChanged = renderDialog();
  await screen.findAllByRole("option", { name: "Sam" });
  await user.selectOptions(within(row("Android")).getByLabelText("Reviewer for Android"), "r2");
  await waitFor(() => expect(changeAssignmentReviewer).toHaveBeenCalledWith("c1", "Android", "r2"));
  expect(onChanged).toHaveBeenCalled();
});

test("retry a failed platform", async () => {
  const user = userEvent.setup();
  retryAssignment.mockResolvedValue(a("iOS", { run_status: "queued", queue_position: 1 }));
  renderDialog();
  await user.click(within(row("iOS")).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(retryAssignment).toHaveBeenCalledWith("c1", "iOS"));
  expect(await within(row("iOS")).findByText("Queued · #1")).toBeInTheDocument();
});

test("re-run a completed platform with a new URL", async () => {
  const user = userEvent.setup();
  rerunAssignment.mockResolvedValue(a("Android", { run_status: "queued", queue_position: 1, devops_url: "https://dev.azure.com/o/p/_git/fixed" }));
  renderDialog();
  await user.click(within(row("Android")).getByRole("button", { name: "Re-run" }));
  const input = screen.getByLabelText("New DevOps URL for Android");
  await user.clear(input);
  await user.type(input, "https://dev.azure.com/o/p/_git/fixed");
  await user.click(screen.getByRole("button", { name: "Queue re-run" }));
  await waitFor(() => expect(rerunAssignment).toHaveBeenCalledWith("c1", "Android", { devopsUrl: "https://dev.azure.com/o/p/_git/fixed" }));
  expect(screen.queryByLabelText("New DevOps URL for Android")).not.toBeInTheDocument();
});

test("shows API errors", async () => {
  const user = userEvent.setup();
  retryAssignment.mockRejectedValue({ response: { data: { detail: "Only a failed review can be retried." } } });
  renderDialog();
  await user.click(within(row("iOS")).getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Only a failed review can be retried.")).toBeInTheDocument();
});

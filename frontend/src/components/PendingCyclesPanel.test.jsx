import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PendingCyclesPanel from "./PendingCyclesPanel";
import { getMyCycles, submitAssignmentUrl, submitAssignmentZip } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getMyCycles: jest.fn(), submitAssignmentUrl: jest.fn(), submitAssignmentZip: jest.fn() }));

const base = { reviewer_id: "r", reviewer_name: "Rae", devops_url: null, devops_branch: null, run_phase: null, run_progress: null,
  run_error: null, failure_kind: null, review_id: null, review_status: null, attempts: 0, queue_position: null };
const cycle = (assignments) => [{ id: "c1", project_id: "p1", project_name: "Moove", year: 2026, quarter: 4, initiated_at: "2026-10-07T00:00:00Z", assignments }];

beforeEach(() => jest.resetAllMocks());

function renderPanel() {
  return render(<MemoryRouter><PendingCyclesPanel /></MemoryRouter>);
}

test("renders nothing when there are no pending cycles", async () => {
  getMyCycles.mockResolvedValue([]);
  const { container } = renderPanel();
  await waitFor(() => expect(getMyCycles).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

test("shows each platform's status and the right action", async () => {
  getMyCycles.mockResolvedValue(cycle([
    { ...base, platform: "Android", run_status: "waiting_for_url" },
    { ...base, platform: "iOS", run_status: "failed", run_error: "Repository or branch not found.", devops_url: "https://dev.azure.com/o/p/_git/bad" },
    { ...base, platform: ".NET", run_status: "completed", review_id: "r9", review_status: "pending_approval", devops_url: "https://dev.azure.com/o/p/_git/ok" },
  ]));
  renderPanel();
  const panel = await screen.findByRole("region", { name: "Pending quarterly reviews" });
  expect(within(panel).getByText("Moove · Q4 2026 review")).toBeInTheDocument();
  expect(within(panel).getByRole("button", { name: "Save & queue" })).toBeInTheDocument();
  expect(within(panel).getByText("Repository or branch not found.")).toBeInTheDocument();
  expect(within(panel).getByLabelText("DevOps URL for iOS")).toHaveValue("https://dev.azure.com/o/p/_git/bad");
  expect(within(panel).getByRole("button", { name: "Save & retry" })).toBeInTheDocument();
  expect(within(panel).getByRole("link", { name: "View" })).toHaveAttribute("href", "/reports/r9");
});

test("saving a URL queues it", async () => {
  const user = userEvent.setup();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "waiting_for_url" }]));
  submitAssignmentUrl.mockResolvedValue({ ...base, platform: "Android", run_status: "queued", queue_position: 1, devops_url: "https://dev.azure.com/o/p/_git/r" });
  renderPanel();
  await user.type(await screen.findByLabelText("DevOps URL for Android"), "https://dev.azure.com/o/p/_git/r");
  await user.type(screen.getByLabelText("Branch for Android"), "develop");
  await user.click(screen.getByRole("button", { name: "Save & queue" }));
  await waitFor(() => expect(submitAssignmentUrl).toHaveBeenCalledWith("c1", "Android", { devopsUrl: "https://dev.azure.com/o/p/_git/r", devopsBranch: "develop" }));
  expect(await screen.findByText("Queued · #1")).toBeInTheDocument();
});

test("shows the API error when saving fails", async () => {
  const user = userEvent.setup();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "waiting_for_url" }]));
  submitAssignmentUrl.mockRejectedValue({ response: { data: { detail: "Not a recognized Azure DevOps repo URL." } } });
  renderPanel();
  await user.type(await screen.findByLabelText("DevOps URL for Android"), "https://github.com/x");
  await user.click(screen.getByRole("button", { name: "Save & queue" }));
  expect(await screen.findByText("Not a recognized Azure DevOps repo URL.")).toBeInTheDocument();
});

test("refreshes every 10s while something is queued or running", async () => {
  jest.useFakeTimers();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "running", run_phase: "scoring", run_progress: 40 }]));
  renderPanel();
  expect(await screen.findByText("Running · Scoring 40%")).toBeInTheDocument();
  expect(getMyCycles).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(10000); });
  expect(getMyCycles).toHaveBeenCalledTimes(2);
  jest.useRealTimers();
});

test("a PM can upload a source zip instead of a URL", async () => {
  const user = userEvent.setup();
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "waiting_for_url" }]));
  submitAssignmentZip.mockResolvedValue({ ...base, platform: "Android", run_status: "queued", queue_position: 1, source_type: "zip", source_zip_name: "android-app.zip" });
  renderPanel();
  await user.click(await screen.findByRole("button", { name: "Upload .zip" }));
  expect(screen.queryByLabelText("DevOps URL for Android")).not.toBeInTheDocument();
  const upload = screen.getByRole("button", { name: "Upload & queue" });
  expect(upload).toBeDisabled();
  const file = new File(["PK"], "android-app.zip", { type: "application/zip" });
  await user.upload(screen.getByLabelText("Source zip for Android"), file);
  await user.click(upload);
  await waitFor(() => expect(submitAssignmentZip).toHaveBeenCalledWith("c1", "Android", file));
  expect(await screen.findByText("Queued · #1")).toBeInTheDocument();
  expect(screen.getByText("Zip: android-app.zip")).toBeInTheDocument();
});

test("a failed zip run offers the zip upload again", async () => {
  getMyCycles.mockResolvedValue(cycle([{ ...base, platform: "Android", run_status: "failed", source_type: "zip", source_zip_name: "old.zip", run_error: "This doesn't look like an Android project." }]));
  renderPanel();
  expect(await screen.findByRole("button", { name: "Upload & retry" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload .zip" })).toHaveAttribute("aria-pressed", "true");
});

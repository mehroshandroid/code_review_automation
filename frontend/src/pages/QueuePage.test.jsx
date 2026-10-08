import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import QueuePage from "./QueuePage";
import {
  getQueue, pauseQueue, resumeQueue, stopQueueItem, removeQueueItem, moveQueueItemToFront, retryAssignment,
} from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getQueue: jest.fn(), pauseQueue: jest.fn(), resumeQueue: jest.fn(), stopQueueItem: jest.fn(),
  removeQueueItem: jest.fn(), moveQueueItemToFront: jest.fn(), retryAssignment: jest.fn(),
}));

const base = { reviewer_name: "Rae", devops_url: "https://dev.azure.com/o/p/_git/r", devops_branch: null, run_phase: null,
  run_progress: null, run_error: null, failure_kind: null, review_id: null, review_status: null, attempts: 1,
  queue_position: null, cancel_requested: null, override_llm_provider: null, override_llm_model: null,
  override_compile_mode: null, project_name: "Alpha", project_id: "p1", year: 2026, quarter: 4,
  queued_at: "2026-10-08T08:00:00Z", started_at: null, finished_at: null };
const snapshot = (extra = {}) => ({
  paused: false, paused_by_name: null, paused_at: null, waiting_for_url: 2,
  defaults: { llm_provider: "azure", llm_model: null, compile_modes: { Android: "compiler", ".NET": "compiler", iOS: "static" } },
  running: [{ ...base, cycle_id: "c1", platform: "Android", run_status: "running", run_phase: "scoring", run_progress: 40, started_at: "2026-10-08T08:01:00Z" }],
  queued: [
    { ...base, cycle_id: "c1", platform: "iOS", run_status: "queued", queue_position: 1 },
    { ...base, cycle_id: "c1", platform: ".NET", run_status: "queued", queue_position: 2, override_llm_provider: "claude" },
  ],
  failed: [{ ...base, cycle_id: "c2", platform: "Android", run_status: "failed", failure_kind: "url", run_error: "Repository or branch not found.", finished_at: "2026-10-08T07:00:00Z" }],
  completed: [{ ...base, cycle_id: "c3", platform: "iOS", run_status: "completed", review_id: "rv1", started_at: "2026-10-08T06:00:00Z", finished_at: "2026-10-08T06:12:00Z" }],
  ...extra,
});

beforeEach(() => {
  jest.resetAllMocks();
  getQueue.mockResolvedValue(snapshot());
});

function renderPage() {
  return render(<MemoryRouter><QueuePage /></MemoryRouter>);
}

test("shows status, panels and items", async () => {
  renderPage();
  expect(await screen.findByText("Running")).toBeInTheDocument();
  const running = screen.getByRole("region", { name: "Running now" });
  expect(within(running).getByText("Alpha · Android · Q4 2026")).toBeInTheDocument();
  expect(within(running).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  const queued = screen.getByRole("region", { name: "Queued" });
  expect(within(queued).getAllByRole("listitem")).toHaveLength(2);
  expect(within(queued).getByText("LLM: Claude CLI (local)")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Failed" })).getByText("Repository or branch not found.")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Recently completed" })).getByRole("link", { name: "View" })).toHaveAttribute("href", "/reports/rv1");
  expect(screen.getByText(/2 waiting for a URL/)).toBeInTheDocument();
});

test("polls every 5 seconds", async () => {
  jest.useFakeTimers();
  renderPage();
  await act(async () => {});
  expect(getQueue).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(getQueue).toHaveBeenCalledTimes(2);
  jest.useRealTimers();
});

test("pause asks for confirmation, resume does not", async () => {
  const user = userEvent.setup();
  pauseQueue.mockResolvedValue(snapshot({ paused: true, paused_by_name: "Ada", paused_at: "2026-10-08T08:05:00Z" }));
  renderPage();
  await user.click(await screen.findByRole("button", { name: "Pause queue" }));
  expect(screen.getByText(/stopped and restarted from the beginning/)).toBeInTheDocument();
  getQueue.mockResolvedValue(snapshot({ paused: true, paused_by_name: "Ada", paused_at: "2026-10-08T08:05:00Z" }));
  await user.click(screen.getByRole("button", { name: "Pause" }));
  await waitFor(() => expect(pauseQueue).toHaveBeenCalled());
  expect(await screen.findByText(/Paused by Ada/)).toBeInTheDocument();
  resumeQueue.mockResolvedValue(snapshot());
  await user.click(screen.getByRole("button", { name: "Resume queue" }));
  await waitFor(() => expect(resumeQueue).toHaveBeenCalled());
});

test("item actions call the API", async () => {
  const user = userEvent.setup();
  [stopQueueItem, removeQueueItem, moveQueueItemToFront, retryAssignment].forEach((fn) => fn.mockResolvedValue({}));
  renderPage();
  const queued = await screen.findByRole("region", { name: "Queued" });
  const dotnet = within(queued).getAllByRole("listitem")[1];
  await user.click(within(dotnet).getByRole("button", { name: "Move to front" }));
  await waitFor(() => expect(moveQueueItemToFront).toHaveBeenCalledWith("c1", ".NET"));
  expect(within(within(queued).getAllByRole("listitem")[0]).queryByRole("button", { name: "Move to front" })).not.toBeInTheDocument();
  await user.click(within(dotnet).getByRole("button", { name: "Remove" }));
  await user.click(screen.getByRole("button", { name: "Remove from queue" }));
  await waitFor(() => expect(removeQueueItem).toHaveBeenCalledWith("c1", ".NET"));
  await user.click(within(screen.getByRole("region", { name: "Running now" })).getByRole("button", { name: "Stop" }));
  await user.click(screen.getByRole("button", { name: "Stop review" }));
  await waitFor(() => expect(stopQueueItem).toHaveBeenCalledWith("c1", "Android"));
  await user.click(within(screen.getByRole("region", { name: "Failed" })).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(retryAssignment).toHaveBeenCalledWith("c2", "Android"));
});

test("a stop in progress shows Stopping…", async () => {
  getQueue.mockResolvedValue(snapshot({ running: [{ ...snapshot().running[0], cancel_requested: "stop" }] }));
  renderPage();
  expect(await screen.findByText("Stopping…")).toBeInTheDocument();
});

test("empty states", async () => {
  getQueue.mockResolvedValue(snapshot({ running: [], queued: [], failed: [], completed: [], waiting_for_url: 0 }));
  renderPage();
  expect(await screen.findByText("Idle")).toBeInTheDocument();
  expect(screen.getByText("Nothing is running.")).toBeInTheDocument();
  expect(screen.getByText("The queue is empty.")).toBeInTheDocument();
});

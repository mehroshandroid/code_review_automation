import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { createReview, getProgress } from "./services/api";

jest.mock("./services/api", () => ({
  ...jest.requireActual("./services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

async function uploadValidFiles(user) {
  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));
}

test("full happy path: upload, poll, complete, download link, LLM stats, reset", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
    category_scores: [
      { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
    ],
    code_context: "class MainActivity {}",
    prompt_log: [
      {
        label: "Code naming conventions / Code Structure",
        prompt_text: "Score the following...",
        tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
      },
    ],
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/review ready/i)).toBeInTheDocument();
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
  expect(screen.getAllByText("Code naming conventions / Code Structure").length).toBeGreaterThan(0);
  expect(screen.getByText("1 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("540 tokens used")).toBeInTheDocument();
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /download populated workbook/i })).toHaveAttribute(
    "href",
    "http://localhost:8000/api/reviews/abc-123/download"
  );

  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("shows an error message when review creation fails", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockRejectedValue(new Error("network error"));

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/failed to start review/i)).toBeInTheDocument();
});

test("shows an error message when the review itself fails during processing, and Try again resets to idle", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "error", phase: "error", progress: 0, message: "Queued",
    stats: {}, download_url: null, error: "No source files found (.java/.kt)",
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    category_scores: [], code_context: null, prompt_log: [],
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText("No source files found (.java/.kt)")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /try again/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

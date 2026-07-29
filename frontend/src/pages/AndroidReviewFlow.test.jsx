import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AndroidReviewFlow from "./AndroidReviewFlow";
import { createReview, getProgress, getOllamaModels } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
  getOllamaModels: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
  localStorage.clear();
  localStorage.setItem("llmProvider", "azure");
  getOllamaModels.mockResolvedValue([]);
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

function renderFlow() {
  return render(
    <MemoryRouter>
      <AndroidReviewFlow />
    </MemoryRouter>
  );
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
    project_name: "project",
    category_scores: [
      {
        id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0,
        sub_criteria: [{ id: "1.1", description: "Clear naming", score: 1, remark: "" }],
      },
    ],
    code_context: "class MainActivity {}",
    prompt_log: [
      {
        label: "Code naming conventions / Code Structure",
        prompt_text: "Score the following...",
        tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
      },
    ],
    lint_issues: [],
    compile_status: "ok",
  });

  renderFlow();
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
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.queryByText(/show source code sent to the model/i)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Debug info" }));
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
  expect(screen.queryByText("1.1")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Report" }));
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.queryByText(/show source code sent to the model/i)).not.toBeInTheDocument();

  expect(screen.getByText("No Lint warnings or errors found.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /download populated workbook/i })).toHaveAttribute(
    "href",
    "http://localhost:8000/api/reviews/abc-123/download"
  );
  expect(screen.getByText("← Home")).toHaveAttribute("href", "/");

  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("shows the project name in the header once progress data has it, falling back beforehand", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: {}, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    project_name: "MyAndroidApp",
    category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: "ok",
  });

  renderFlow();
  expect(screen.getByRole("heading", { name: "Android Code Review Automation" })).toBeInTheDocument();

  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByRole("heading", { name: "MyAndroidApp" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Android Code Review Automation" })).not.toBeInTheDocument();
});

test("shows an error message when review creation fails", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockRejectedValue(new Error("network error"));

  renderFlow();
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
    project_name: null,
    category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText("No source files found (.java/.kt)")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /try again/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("sends the selected Ollama provider and model when available", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  localStorage.setItem("llmProvider", "ollama");
  localStorage.setItem("ollamaModel", "qwen2.5-coder:7b");
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b", "compiler", "Android");
});

test("falls back to Azure when Ollama is selected but no models are installed", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  localStorage.setItem("llmProvider", "ollama");
  getOllamaModels.mockResolvedValue([]);
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android");
});

test("shows the compile-check mode toggle", () => {
  renderFlow();
  expect(screen.getByRole("button", { name: "Compile-time lint" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Static file analysis" })).toBeInTheDocument();
});

test("sends the persisted compile-check mode when starting a review", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  localStorage.setItem("compileCheckMode", "static");
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "static", "Android");
});

test("sends the platform label from a custom platform prop instead of the default", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  render(
    <MemoryRouter>
      <AndroidReviewFlow platform={{ id: "android", label: "AndroidCustom" }} />
    </MemoryRouter>
  );
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "AndroidCustom");
});

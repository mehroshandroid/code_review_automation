import { act, render, screen } from "@testing-library/react";
import ProgressTracker from "./ProgressTracker";
import { getProgress } from "../services/api";

jest.mock("../services/api");

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

test("shows all five steps before the first poll resolves", () => {
  getProgress.mockReturnValue(new Promise(() => {}));

  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);

  expect(screen.getByText("Extracting archive")).toBeInTheDocument();
  expect(screen.getByText("Analyzing code")).toBeInTheDocument();
  expect(screen.getByText("Compiling & linting")).toBeInTheDocument();
  expect(screen.getByText("Scoring with AI")).toBeInTheDocument();
  expect(screen.getByText("Generating report")).toBeInTheDocument();
});

test("polls immediately on mount and shows the active phase's live message", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting project files...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null,
  });
  const onUpdate = jest.fn();

  render(<ProgressTracker reviewId="abc-123" onUpdate={onUpdate} />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledWith("abc-123");
  expect(screen.getByText("Extracting project files...")).toBeInTheDocument();
  expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ phase: "extracting" }));
});

test("shows the scoring phase's per-category message as subtext", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "scoring", progress: 60,
    message: "Evaluating Reliability, Security & Observability...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null,
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(screen.getByText("Evaluating Reliability, Security & Observability...")).toBeInTheDocument();
});

test("polls again after 2000ms while status is processing", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "scoring", progress: 60, message: "Scoring...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null,
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(getProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(2000);
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledTimes(2);
});

test("stops polling once status is completed", async () => {
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: 78,
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(getProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(2000);
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledTimes(1);
});

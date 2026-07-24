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

test("polls immediately on mount and shows the returned phase", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
  });
  const onUpdate = jest.fn();

  render(<ProgressTracker reviewId="abc-123" onUpdate={onUpdate} />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledWith("abc-123");
  expect(screen.getByText("extracting")).toBeInTheDocument();
  expect(screen.getByText("Extracting...")).toBeInTheDocument();
  expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ phase: "extracting" }));
});

test("polls again after 2000ms while status is processing", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "scoring", progress: 60, message: "Scoring...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
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
    warnings: [], test_coverage: null, secrets_found: [],
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

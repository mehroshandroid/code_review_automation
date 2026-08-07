import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ReviewReportPage from "./ReviewReportPage";
import { getReview, updateReview } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getReview: jest.fn(),
  updateReview: jest.fn(),
}));

function renderReport(reviewId = "r1") {
  return render(
    <MemoryRouter initialEntries={[`/reports/${reviewId}`]}>
      <Routes>
        <Route path="/reports/:reviewId" element={<ReviewReportPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const review = {
  id: "r1",
  project_id: "p1",
  platform: ".NET",
  status: "pending_approval",
  project_name: "Moove",
  created_at: "2026-08-01T00:00:00Z",
  completed_at: "2026-08-01T00:05:00Z",
  total_score_pct: 82.5,
  llm_provider: "azure",
  llm_model: null,
  has_workbook: true,
  category_scores: [
    { id: "1", name: "Structure", percent_points: 100, sub_criteria: [{ id: "1.1", description: "Naming", score: 1, remark: "Good" }] },
  ],
  warnings: ["Outdated SDK"],
  secrets_found: [],
  lint_issues: [],
  compile_status: "ok",
  stats: {},
  error: null,
};

test("renders the review's project name, platform, and score once loaded", async () => {
  getReview.mockResolvedValue(review);
  renderReport();

  expect(await screen.findByText("Moove")).toBeInTheDocument();
  expect(screen.getByText(".NET")).toBeInTheDocument();
  expect(screen.getByText("Total 82.5%")).toBeInTheDocument();
});

test("renders the category scores via the report table", async () => {
  getReview.mockResolvedValue(review);
  renderReport();

  expect(await screen.findByText("Structure")).toBeInTheDocument();
  expect(screen.getByText("Naming")).toBeInTheDocument();
  expect(screen.getByText("Good")).toBeInTheDocument();
});

test("shows a download link when the review has a workbook", async () => {
  getReview.mockResolvedValue(review);
  renderReport();

  const link = await screen.findByRole("link", { name: /download/i });
  expect(link).toHaveAttribute("href", expect.stringContaining("/api/reviews/r1/download"));
});

test("omits the download link when the review has no workbook", async () => {
  getReview.mockResolvedValue({ ...review, has_workbook: false });
  renderReport();

  await screen.findByText("Moove");
  expect(screen.queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
});

test("shows a not-found state when the review doesn't exist", async () => {
  getReview.mockRejectedValue({ response: { status: 404 } });
  renderReport("does-not-exist");

  expect(await screen.findByText(/review not found/i)).toBeInTheDocument();
});

test("shows approval status buttons and an Edit scores button when there are category scores", async () => {
  getReview.mockResolvedValue(review);
  renderReport();

  await screen.findByText("Moove");
  expect(screen.getByRole("button", { name: "Pending approval" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Approved" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Completed" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /edit scores/i })).toBeInTheDocument();
});

test("hides the approval section when the review has no category scores (e.g. an errored review)", async () => {
  getReview.mockResolvedValue({ ...review, status: "error", category_scores: [], error: "boom" });
  renderReport();

  await screen.findByText("Moove");
  expect(screen.queryByRole("button", { name: /edit scores/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approved" })).not.toBeInTheDocument();
});

test("clicking a status button updates the review's status", async () => {
  const user = userEvent.setup();
  getReview.mockResolvedValue(review);
  updateReview.mockResolvedValue({ ...review, status: "approved" });
  renderReport();

  await screen.findByText("Moove");
  await user.click(screen.getByRole("button", { name: "Approved" }));

  await waitFor(() => expect(updateReview).toHaveBeenCalledWith("r1", { status: "approved" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Approved" })).toHaveClass("btn-primary"));
});

test("clicking Edit scores switches the report table into edit mode with score selects", async () => {
  const user = userEvent.setup();
  getReview.mockResolvedValue(review);
  renderReport();

  await screen.findByText("Moove");
  await user.click(screen.getByRole("button", { name: /edit scores/i }));

  expect(screen.getByLabelText(/score for 1\.1/i)).toHaveValue("1");
  expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
});

test("editing a score and saving calls updateReview with the edited category scores and replaces the review", async () => {
  const user = userEvent.setup();
  getReview.mockResolvedValue(review);
  const updated = {
    ...review,
    total_score_pct: 0,
    category_scores: [
      { id: "1", name: "Structure", percent_points: 0, sub_criteria: [{ id: "1.1", description: "Naming", score: 0, remark: "Actually not great" }] },
    ],
  };
  updateReview.mockResolvedValue(updated);
  renderReport();

  await screen.findByText("Moove");
  await user.click(screen.getByRole("button", { name: /edit scores/i }));
  await user.selectOptions(screen.getByLabelText(/score for 1\.1/i), "0");
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => expect(updateReview).toHaveBeenCalledWith("r1", {
    categoryScores: [
      { id: "1", name: "Structure", percent_points: 100, sub_criteria: [{ id: "1.1", description: "Naming", score: 0, remark: "Good" }] },
    ],
  }));
  expect(await screen.findByText("Actually not great")).toBeInTheDocument();
  expect(screen.queryByLabelText(/score for 1\.1/i)).not.toBeInTheDocument();
});

test("clicking Cancel discards edits and exits edit mode without saving", async () => {
  const user = userEvent.setup();
  getReview.mockResolvedValue(review);
  renderReport();

  await screen.findByText("Moove");
  await user.click(screen.getByRole("button", { name: /edit scores/i }));
  await user.selectOptions(screen.getByLabelText(/score for 1\.1/i), "0");
  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(updateReview).not.toHaveBeenCalled();
  expect(screen.queryByLabelText(/score for 1\.1/i)).not.toBeInTheDocument();
  expect(screen.getByText("Good")).toBeInTheDocument();
});

test("shows an error message when saving edits fails", async () => {
  const user = userEvent.setup();
  getReview.mockResolvedValue(review);
  updateReview.mockRejectedValue(new Error("network error"));
  renderReport();

  await screen.findByText("Moove");
  await user.click(screen.getByRole("button", { name: /edit scores/i }));
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  expect(await screen.findByText(/failed to save changes/i)).toBeInTheDocument();
});

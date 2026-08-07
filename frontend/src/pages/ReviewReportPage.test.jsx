import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ReviewReportPage from "./ReviewReportPage";
import { getReview } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getReview: jest.fn(),
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

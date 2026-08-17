import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectReviewHistory from "./ProjectReviewHistory";
import { getProjectReviews } from "../services/api";

jest.mock("../services/api");

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
});

function renderHistory(projectId = "p1") {
  return render(
    <MemoryRouter>
      <ProjectReviewHistory projectId={projectId} />
    </MemoryRouter>
  );
}

const reviews = [
  { id: "r2", platform: "Android", status: "pending_approval", created_at: "2026-08-02T00:00:00Z", completed_at: "2026-08-02T00:05:00Z", total_score_pct: 90 },
  { id: "r1", platform: ".NET", status: "error", created_at: "2026-08-01T00:00:00Z", completed_at: null, total_score_pct: null },
];

function buildReview(overrides) {
  return {
    id: "r", platform: "Android", status: "pending_approval",
    created_at: "2026-08-01T00:00:00Z", completed_at: "2026-08-01T00:05:00Z",
    total_score_pct: 80,
    category_scores: [
      { id: "1", name: "Structure", percent_points: 83.3 },
      { id: "2", name: "Security", percent_points: 55 },
    ],
    ...overrides,
  };
}

test("fetches and renders a table row for every review", async () => {
  getProjectReviews.mockResolvedValue(reviews);
  renderHistory();

  expect(await screen.findByText("Android")).toBeInTheDocument();
  expect(screen.getByText(".NET")).toBeInTheDocument();
  expect(screen.getByText("90%")).toBeInTheDocument();
});

test("refetches when the projectId prop changes", async () => {
  getProjectReviews.mockResolvedValue(reviews);
  const { rerender } = renderHistory("p1");
  await screen.findByText("Android");

  getProjectReviews.mockClear();
  getProjectReviews.mockResolvedValue([]);
  rerender(
    <MemoryRouter>
      <ProjectReviewHistory projectId="p2" />
    </MemoryRouter>
  );

  await screen.findByText(/no reviews yet/i);
  expect(getProjectReviews).toHaveBeenCalledWith("p2");
});

test("shows an empty state when the project has no reviews", async () => {
  getProjectReviews.mockResolvedValue([]);
  renderHistory();

  expect(await screen.findByText(/no reviews yet/i)).toBeInTheDocument();
});

test("navigates to the report page when a row is clicked", async () => {
  const user = userEvent.setup();
  getProjectReviews.mockResolvedValue(reviews);
  renderHistory();

  await screen.findByText("Android");
  await user.click(screen.getByText("Android"));

  expect(mockNavigate).toHaveBeenCalledWith("/reports/r2");
});

test("renders a chart section per platform with chartable review data", async () => {
  getProjectReviews.mockResolvedValue([
    buildReview({ id: "r1", platform: "Android" }),
    buildReview({ id: "r2", platform: ".NET", category_scores: [{ id: "1", name: "Structure", percent_points: 70 }] }),
  ]);
  renderHistory();

  expect(await screen.findByText(/android clause scores/i)).toBeInTheDocument();
  expect(screen.getByText(/\.net clause scores/i)).toBeInTheDocument();
});

test("does not render a chart section for a platform whose only reviews are errored or have no category data", async () => {
  getProjectReviews.mockResolvedValue([
    buildReview({ id: "r1", platform: "iOS", status: "error", category_scores: [] }),
  ]);
  renderHistory();

  await screen.findByText("iOS"); // still present in the table below
  expect(screen.queryByText(/ios clause scores/i)).not.toBeInTheDocument();
});

test("limits each platform's chart to its 5 most recent reviews", async () => {
  // API returns newest first -- 08-06 is the newest, 08-01 the oldest of 6.
  const dates = ["2026-08-06", "2026-08-05", "2026-08-04", "2026-08-03", "2026-08-02", "2026-08-01"];
  getProjectReviews.mockResolvedValue(dates.map((date, index) => buildReview({ id: `r${index}`, created_at: `${date}T00:00:00Z` })));
  renderHistory();

  const chartSection = (await screen.findByText(/android clause scores/i)).closest(".card");
  const newestLabel = new Date("2026-08-06T00:00:00Z").toLocaleDateString();
  const oldestLabel = new Date("2026-08-01T00:00:00Z").toLocaleDateString();
  expect(within(chartSection).getByText(newestLabel)).toBeInTheDocument();
  expect(within(chartSection).queryByText(oldestLabel)).not.toBeInTheDocument();
});

test("renders a bar series per clause/category present in the platform's data", async () => {
  getProjectReviews.mockResolvedValue([buildReview({ id: "r1" })]);
  renderHistory();

  const chartSection = (await screen.findByText(/android clause scores/i)).closest(".card");
  expect(within(chartSection).getByText("Structure")).toBeInTheDocument();
  expect(within(chartSection).getByText("Security")).toBeInTheDocument();
});

test("the history table still lists every review, including errored ones without a chart", async () => {
  getProjectReviews.mockResolvedValue([
    buildReview({ id: "r1", platform: "iOS", status: "error", category_scores: [], total_score_pct: null }),
  ]);
  renderHistory();

  expect(await screen.findByText("iOS")).toBeInTheDocument();
  expect(screen.getByText("Error")).toBeInTheDocument();
});

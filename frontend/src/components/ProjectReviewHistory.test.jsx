import { render, screen } from "@testing-library/react";
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

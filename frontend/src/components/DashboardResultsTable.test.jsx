import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import DashboardResultsTable from "./DashboardResultsTable";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
});

function renderTable(reviews) {
  return render(
    <MemoryRouter>
      <DashboardResultsTable reviews={reviews} />
    </MemoryRouter>
  );
}

const reviews = [
  { id: "r1", project_name: "Moove", platform: ".NET", status: "pending_approval", created_at: "2026-08-01T00:00:00Z", total_score_pct: 80 },
  { id: "r2", project_name: "Payments", platform: "Android", status: "error", created_at: "2026-08-02T00:00:00Z", total_score_pct: null },
];

test("renders a row per review including errored ones, with the project name shown", () => {
  renderTable(reviews);

  expect(screen.getByText("Moove")).toBeInTheDocument();
  expect(screen.getByText("Payments")).toBeInTheDocument();
  expect(screen.getByText("Error")).toBeInTheDocument();
  expect(screen.getByText("80%")).toBeInTheDocument();
});

test("shows an em dash for a review with no score", () => {
  renderTable(reviews);
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("navigates to the report page when a row is clicked", async () => {
  const user = userEvent.setup();
  renderTable(reviews);

  await user.click(screen.getByText("Moove"));

  expect(mockNavigate).toHaveBeenCalledWith("/reports/r1");
});

test("shows an empty state when there are no reviews", () => {
  renderTable([]);
  expect(screen.getByText(/no reviews match/i)).toBeInTheDocument();
});

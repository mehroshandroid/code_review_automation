import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MyReviewsPage from "./MyReviewsPage";
import { getMyReviews } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getMyReviews: jest.fn() }));

const rows = [
  { id: "r1", project_name: "Alpha", platform: "Android", status: "pending_approval", created_at: "2026-05-01T00:00:00Z", total_score_pct: 72.5 },
  { id: "r2", project_name: "Beta", platform: "iOS", status: "approved", created_at: "2026-04-01T00:00:00Z", total_score_pct: 90 },
];

function renderPage() {
  return render(<MemoryRouter><MyReviewsPage /></MemoryRouter>);
}

test("defaults to pending reviews and links to the report", async () => {
  getMyReviews.mockResolvedValue(rows);
  renderPage();
  const table = await screen.findByRole("table");
  expect(within(table).getByText("Alpha")).toBeInTheDocument();
  expect(within(table).queryByText("Beta")).not.toBeInTheDocument();
  expect(within(table).getByRole("link", { name: /open/i })).toHaveAttribute("href", "/reports/r1");
});

test("All shows approved reviews too", async () => {
  const user = userEvent.setup();
  getMyReviews.mockResolvedValue(rows);
  renderPage();
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "All" }));
  expect(screen.getByText("Beta")).toBeInTheDocument();
});

test("empty state", async () => {
  getMyReviews.mockResolvedValue([]);
  renderPage();
  expect(await screen.findByText("No reviews assigned to you.")).toBeInTheDocument();
});

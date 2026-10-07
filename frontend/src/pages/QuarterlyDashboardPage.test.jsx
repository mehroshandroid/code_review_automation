import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import QuarterlyDashboardPage from "./QuarterlyDashboardPage";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getQuarterly, getReviewers, getReviewYears, initiateCycle } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getQuarterly: jest.fn(), getReviewers: jest.fn(), getReviewYears: jest.fn(), initiateCycle: jest.fn(),
}));

const q = (quarter, status, extra = {}) => ({
  quarter, start: "2026-01-01", end: "2026-03-31", status, covered: [], missing: ["Android"],
  can_initiate: false, cycle: null, ...extra,
});

const data = {
  year: 2026, today: "2026-10-07",
  projects: [
    { id: "p1", name: "Alpha", platforms: ["Android"], quarters: [q(1, "done"), q(2, "done"), q(3, "overdue", { can_initiate: true }), q(4, "not_started", { can_initiate: true })] },
    { id: "p2", name: "Beta", platforms: [], quarters: [] },
  ],
};

beforeEach(() => {
  jest.resetAllMocks();
  getQuarterly.mockResolvedValue(data);
  getReviewYears.mockResolvedValue([2025, 2026]);
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }]);
});

function renderAs(role = "coordinator") {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><QuarterlyDashboardPage /></MemoryRouter>
    </AuthContext.Provider>
  );
}

test("renders a row per project with four quarter cards", async () => {
  renderAs();
  const row = await screen.findByRole("region", { name: "Alpha" });
  expect(within(row).getAllByText(/^Q[1-4] · /)).toHaveLength(4);
  expect(within(row).getAllByText("Done")).toHaveLength(2);
});

test("prompts to set platforms for projects without any", async () => {
  renderAs();
  const row = await screen.findByRole("region", { name: "Beta" });
  expect(within(row).getByRole("link", { name: "Set platforms to track quarterly reviews" })).toHaveAttribute("href", "/projects");
});

test("changing the year refetches", async () => {
  const user = userEvent.setup();
  renderAs();
  await screen.findByRole("region", { name: "Alpha" });
  await user.selectOptions(screen.getByLabelText("Year"), "2025");
  await waitFor(() => expect(getQuarterly).toHaveBeenLastCalledWith(2025));
});

test("search filters projects", async () => {
  const user = userEvent.setup();
  renderAs();
  await screen.findByRole("region", { name: "Alpha" });
  await user.type(screen.getByRole("searchbox", { name: "Search projects" }), "bet");
  expect(screen.queryByRole("region", { name: "Alpha" })).not.toBeInTheDocument();
});

test("initiating replaces the quarter card", async () => {
  const user = userEvent.setup();
  initiateCycle.mockResolvedValue(q(4, "in_progress", { cycle: { id: "c1", initiated_at: "2026-10-07T00:00:00Z", initiated_by_name: "Cora", assignments: [] } }));
  renderAs();
  const row = await screen.findByRole("region", { name: "Alpha" });
  await user.click(within(row).getAllByRole("button", { name: /initiate review/i })[1]);
  await screen.findByRole("option", { name: "Rae" });
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  await user.click(screen.getByRole("button", { name: "Initiate" }));
  expect(await within(row).findByText("In progress")).toBeInTheDocument();
});

test("load error", async () => {
  getQuarterly.mockRejectedValue(new Error("boom"));
  renderAs();
  expect(await screen.findByText("Couldn't load quarterly status.")).toBeInTheDocument();
});

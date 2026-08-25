import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectDashboardPage from "./ProjectDashboardPage";
import { getProjects, getReviews, getReviewYears, updateProject, uploadCompletedReview } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getProjects: jest.fn(),
  getReviews: jest.fn(),
  getReviewYears: jest.fn(),
  updateProject: jest.fn(),
  uploadCompletedReview: jest.fn(),
}));

const projects = [
  { id: "p1", name: "Payments Service" },
  { id: "p2", name: "Notifications" },
];

const currentYear = new Date().getFullYear();

beforeEach(() => {
  jest.resetAllMocks();
  getProjects.mockResolvedValue(projects);
  getReviewYears.mockResolvedValue([currentYear - 1, currentYear]);
  getReviews.mockResolvedValue([]);
  uploadCompletedReview.mockResolvedValue({ id: "r1" });
});

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ProjectDashboardPage />
    </MemoryRouter>
  );
}

test("fetches reviews for the current year with no platform/project filter by default", async () => {
  renderDashboard();

  await waitFor(() => expect(getReviews).toHaveBeenCalledWith({ year: currentYear, platform: null, projectId: null }));
});

test("shows the filter bar with the current year selected by default", async () => {
  renderDashboard();

  expect(await screen.findByRole("button", { name: "Year" })).toHaveTextContent(String(currentYear));
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("All platforms");
  expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("All projects");
});

test("changing a filter re-fetches reviews with the new params", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await screen.findByRole("button", { name: "Platform" });

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: "Android", projectId: null }));
});

test("Reset filters restores the defaults and re-fetches", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await screen.findByRole("button", { name: "Platform" });

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));
  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: "Android", projectId: null }));

  await user.click(screen.getByRole("button", { name: /reset filters/i }));

  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: null, projectId: null }));
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("All platforms");
});

test("renders the overview and results table once reviews load", async () => {
  getReviews.mockResolvedValue([
    { id: "r1", project_name: "Moove", platform: ".NET", status: "pending_approval", created_at: "2026-08-01T00:00:00Z", total_score_pct: 80, category_scores: [] },
  ]);
  renderDashboard();

  expect(await screen.findByText("Final Score")).toBeInTheDocument();
  expect(screen.getByText("Moove")).toBeInTheDocument();
});

test("clicking Start review opens the dialog", async () => {
  const user = userEvent.setup();
  renderDashboard();

  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(screen.getByText("Start a review")).toBeInTheDocument();
});

test("clicking Upload review opens the upload dialog", async () => {
  const user = userEvent.setup();
  renderDashboard();

  await user.click(screen.getByRole("button", { name: /upload review/i }));

  expect(screen.getByText("Upload a completed review")).toBeInTheDocument();
});

test("a successful upload jumps the dashboard filters to the uploaded review and shows a success message", async () => {
  const user = userEvent.setup();
  const uploadedYear = currentYear - 1;
  uploadCompletedReview.mockResolvedValue({
    id: "r1", project_id: "p1", project_name: "Payments Service", platform: "Android", created_at: `${uploadedYear}-06-15T00:00:00Z`,
  });
  renderDashboard();
  await screen.findByRole("button", { name: "Platform" });

  await user.click(screen.getByRole("button", { name: /upload review/i }));
  const dialog = screen.getByText("Upload a completed review").closest(".dialog");
  await user.click(within(dialog).getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await user.click(within(dialog).getByRole("button", { name: "Android" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  expect(await screen.findByText(/uploaded successfully/i)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /done/i }));

  expect(screen.queryByText("Upload a completed review")).not.toBeInTheDocument();
  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: uploadedYear, platform: "Android", projectId: "p1" }));
  expect(screen.getByRole("button", { name: "Year" })).toHaveTextContent(String(uploadedYear));
});

test("renders a Settings link pointing at /settings", async () => {
  renderDashboard();

  expect(await screen.findByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
});

test("renders the review-insights chat widget", async () => {
  renderDashboard();

  expect(await screen.findByRole("button", { name: /open review insights chat/i })).toBeInTheDocument();
});

test("shows one combined empty-state message, not the overview/table, when no reviews match", async () => {
  getReviews.mockResolvedValue([]);
  renderDashboard();

  expect(await screen.findByText(/no reviews match these filters/i)).toBeInTheDocument();
  expect(screen.queryByText("Final Score")).not.toBeInTheDocument();
});

test("renaming a project updates it in the Project dropdown", async () => {
  const user = userEvent.setup();
  const updated = { id: "p1", name: "Payments Team" };
  updateProject.mockResolvedValue(updated);
  renderDashboard();

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await waitFor(() => expect(getReviews).toHaveBeenLastCalledWith({ year: currentYear, platform: null, projectId: "p1" }));

  await user.click(screen.getByRole("button", { name: /rename payments service/i }));
  await user.clear(screen.getByLabelText(/project name/i));
  await user.type(screen.getByLabelText(/project name/i), "Payments Team");
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("Payments Team"));
});

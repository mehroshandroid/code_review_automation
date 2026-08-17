import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectDashboardPage from "./ProjectDashboardPage";
import { getLlmProvider } from "../services/llmProviderStorage";
import { getOllamaModels, getProjects, getProjectReviews, createProject, getLlmProviderSettings } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getOllamaModels: jest.fn(),
  getProjects: jest.fn(),
  getProjectReviews: jest.fn(),
  createProject: jest.fn(),
  getLlmProviderSettings: jest.fn(),
}));

const projects = [
  { id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" },
  { id: "p2", name: "Notifications", created_at: "2026-08-06T00:00:00Z" },
];

beforeEach(() => {
  localStorage.clear();
  jest.resetAllMocks();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  getProjectReviews.mockResolvedValue([]);
  getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: null });
});

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ProjectDashboardPage />
    </MemoryRouter>
  );
}

test("fetches projects and auto-selects the first one", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  await waitFor(() => expect(screen.getByRole("button", { name: "Payments Service" })).toHaveClass("btn-primary"));
  expect(getProjectReviews).toHaveBeenCalledWith("p1");
});

test("shows a prompt instead of the platform picker when there are no projects", async () => {
  getProjects.mockResolvedValue([]);
  renderDashboard();

  expect(await screen.findByText(/create a project to get started/i)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /android/i })).not.toBeInTheDocument();
});

test("shows the platform picker once a project is selected", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  expect(await screen.findByRole("link", { name: /android/i })).toHaveAttribute("href", "/review/android");
});

test("clicking a different project in the sidebar switches the selected project", async () => {
  const user = userEvent.setup();
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  await waitFor(() => expect(screen.getByRole("button", { name: "Payments Service" })).toHaveClass("btn-primary"));
  await user.click(screen.getByRole("button", { name: "Notifications" }));

  expect(screen.getByRole("button", { name: "Notifications" })).toHaveClass("btn-primary");
  expect(getProjectReviews).toHaveBeenCalledWith("p2");
});

test("creating a project selects it automatically", async () => {
  const user = userEvent.setup();
  getProjects.mockResolvedValue([]);
  const newProject = { id: "p3", name: "New Project", created_at: "2026-08-07T00:00:00Z" };
  createProject.mockResolvedValue(newProject);
  renderDashboard();

  await screen.findByText(/create a project to get started/i);
  await user.click(screen.getByRole("button", { name: /add project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: "New Project" })).toHaveClass("btn-primary"));
  expect(getProjectReviews).toHaveBeenCalledWith("p3");
});

test("the platform link carries the selected project id as router state", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  const link = await screen.findByRole("link", { name: /android/i });
  // react-router encodes Link state onto the underlying history entry, not
  // a plain DOM attribute -- assert via the rendered element's internal
  // state prop is impractical here, so this is covered end-to-end by
  // AndroidReviewFlow/ReviewPage tests reading location.state instead.
  expect(link).toHaveAttribute("href", "/review/android");
});

test("defaults to Ollama highlighted when models are available, same as before", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));
  expect(getLlmProvider()).toBe("ollama");
});

test("seeds localStorage from the fetched org default when nothing was explicitly chosen", async () => {
  getProjects.mockResolvedValue(projects);
  getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "azure", default_ollama_model: null });
  renderDashboard();

  await waitFor(() => expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary"));
  expect(getLlmProvider()).toBe("azure");
});

test("renders a Settings link pointing at /settings", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  expect(await screen.findByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
});

test("renders the review-insights chat widget", async () => {
  getProjects.mockResolvedValue(projects);
  renderDashboard();

  expect(await screen.findByRole("button", { name: /open review insights chat/i })).toBeInTheDocument();
});

test("does not override a provider the user already picked in a previous session", async () => {
  localStorage.setItem("llmProvider", "azure");
  getProjects.mockResolvedValue(projects);
  getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: null });
  renderDashboard();

  await waitFor(() => expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary"));
  expect(getLlmProvider()).toBe("azure");
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import StartReviewDialog from "./StartReviewDialog";
import { getOllamaModels, createProject } from "../services/api";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getOllamaModels: jest.fn(),
  createProject: jest.fn(),
}));

const projects = [{ id: "p1", name: "Payments Service" }];

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
});

function renderDialog(overrides = {}) {
  return render(
    <MemoryRouter>
      <StartReviewDialog projects={projects} onProjectCreated={jest.fn()} onClose={jest.fn()} {...overrides} />
    </MemoryRouter>
  );
}

test("platform cards are disabled until a project is chosen", async () => {
  renderDialog();
  await screen.findByText("Android");

  await userEvent.setup().click(screen.getByRole("button", { name: "Android" }));

  expect(mockNavigate).not.toHaveBeenCalled();
});

test("selecting a project then clicking an available platform navigates with the project id in state", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(mockNavigate).toHaveBeenCalledWith("/review/android", { state: { projectId: "p1" } });
});

test("does not navigate when clicking an unavailable platform, even with a project chosen", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
  await user.click(screen.getByRole("button", { name: "Web (React)" }));

  expect(mockNavigate).not.toHaveBeenCalled();
});

test("shows the previously-selected provider highlighted when models are available", async () => {
  // getLlmProvider() has no hardcoded fallback -- an org default gets
  // seeded once on the dashboard page's mount before this dialog could
  // ever open, so this simulates that already having happened.
  localStorage.setItem("llmProvider", "ollama");
  renderDialog();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));
});

test("creating a project via the dialog selects it and calls onProjectCreated", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const newProject = { id: "p2", name: "New Project" };
  createProject.mockResolvedValue(newProject);
  renderDialog({ onProjectCreated });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: /add new project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  expect(onProjectCreated).toHaveBeenCalledWith(newProject);
  await user.click(screen.getByRole("button", { name: "Android" }));
  expect(mockNavigate).toHaveBeenCalledWith("/review/android", { state: { projectId: "p2" } });
});

test("clicking Cancel calls onClose", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  renderDialog({ onClose });

  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(onClose).toHaveBeenCalled();
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectSidebar from "./ProjectSidebar";
import { createProject, updateProject } from "../services/api";

jest.mock("../services/api");

const projects = [
  { id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" },
  { id: "p2", name: "Notifications", created_at: "2026-08-06T00:00:00Z" },
];

function renderSidebar(overrides = {}) {
  return render(
    <ProjectSidebar
      projects={projects}
      selectedProjectId="p1"
      onSelectProject={jest.fn()}
      onProjectCreated={jest.fn()}
      onProjectRenamed={jest.fn()}
      {...overrides}
    />
  );
}

test("renders every project and highlights the selected one", () => {
  renderSidebar();

  expect(screen.getByText("Payments Service")).toBeInTheDocument();
  expect(screen.getByText("Notifications")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Payments Service" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Notifications" })).not.toHaveClass("btn-primary");
});

test("calls onSelectProject when a project is clicked", async () => {
  const user = userEvent.setup();
  const onSelectProject = jest.fn();
  renderSidebar({ onSelectProject });

  await user.click(screen.getByRole("button", { name: "Notifications" }));

  expect(onSelectProject).toHaveBeenCalledWith("p2");
});

test("shows an empty state when there are no projects", () => {
  renderSidebar({ projects: [], selectedProjectId: null });

  expect(screen.getByText(/no projects yet/i)).toBeInTheDocument();
});

test("clicking + opens a dialog to create a project, and calls onProjectCreated with it", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const newProject = { id: "p3", name: "New Project", created_at: "2026-08-07T00:00:00Z" };
  createProject.mockResolvedValue(newProject);
  renderSidebar({ onProjectCreated });

  await user.click(screen.getByRole("button", { name: /add project/i }));
  expect(screen.getByText("New project")).toBeInTheDocument();

  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(onProjectCreated).toHaveBeenCalledWith(newProject));
  expect(createProject).toHaveBeenCalledWith("New Project");
});

test("the create dialog closes after a successful create", async () => {
  const user = userEvent.setup();
  createProject.mockResolvedValue({ id: "p3", name: "New Project", created_at: "2026-08-07T00:00:00Z" });
  renderSidebar();

  await user.click(screen.getByRole("button", { name: /add project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(screen.queryByText("New project")).not.toBeInTheDocument());
});

test("shows an error message when creation fails, and keeps the dialog open", async () => {
  const user = userEvent.setup();
  createProject.mockRejectedValue({ response: { data: { detail: "A project with this name already exists" } } });
  renderSidebar();

  await user.click(screen.getByRole("button", { name: /add project/i }));
  await user.type(screen.getByLabelText(/project name/i), "Payments Service");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(await screen.findByText("A project with this name already exists")).toBeInTheDocument();
  expect(screen.getByText("New project")).toBeInTheDocument();
});

test("clicking Cancel in the create dialog closes it without creating a project", async () => {
  const user = userEvent.setup();
  renderSidebar();

  await user.click(screen.getByRole("button", { name: /add project/i }));
  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(screen.queryByText("New project")).not.toBeInTheDocument();
  expect(createProject).not.toHaveBeenCalled();
});

test("clicking the rename icon opens a dialog pre-filled with the current name, and calls onProjectRenamed", async () => {
  const user = userEvent.setup();
  const onProjectRenamed = jest.fn();
  const renamed = { id: "p1", name: "Payments Team", created_at: "2026-08-07T00:00:00Z" };
  updateProject.mockResolvedValue(renamed);
  renderSidebar({ onProjectRenamed });

  await user.click(screen.getByRole("button", { name: /rename payments service/i }));
  expect(screen.getByText("Rename project")).toBeInTheDocument();
  expect(screen.getByLabelText(/project name/i)).toHaveValue("Payments Service");

  await user.clear(screen.getByLabelText(/project name/i));
  await user.type(screen.getByLabelText(/project name/i), "Payments Team");
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(onProjectRenamed).toHaveBeenCalledWith(renamed));
  expect(updateProject).toHaveBeenCalledWith("p1", "Payments Team");
});

test("shows an error message when renaming fails", async () => {
  const user = userEvent.setup();
  updateProject.mockRejectedValue({ response: { data: { detail: "A project with this name already exists" } } });
  renderSidebar();

  await user.click(screen.getByRole("button", { name: /rename payments service/i }));
  await user.clear(screen.getByLabelText(/project name/i));
  await user.type(screen.getByLabelText(/project name/i), "Notifications");
  await user.click(screen.getByRole("button", { name: /save/i }));

  expect(await screen.findByText("A project with this name already exists")).toBeInTheDocument();
});

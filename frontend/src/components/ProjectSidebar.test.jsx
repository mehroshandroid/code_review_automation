import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectSidebar from "./ProjectSidebar";
import { createProject } from "../services/api";

jest.mock("../services/api");

const projects = [
  { id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" },
  { id: "p2", name: "Notifications", created_at: "2026-08-06T00:00:00Z" },
];

test("renders every project and highlights the selected one", () => {
  render(<ProjectSidebar projects={projects} selectedProjectId="p1" onSelectProject={jest.fn()} onProjectCreated={jest.fn()} />);

  expect(screen.getByText("Payments Service")).toBeInTheDocument();
  expect(screen.getByText("Notifications")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Payments Service" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Notifications" })).not.toHaveClass("btn-primary");
});

test("calls onSelectProject when a project is clicked", async () => {
  const user = userEvent.setup();
  const onSelectProject = jest.fn();
  render(<ProjectSidebar projects={projects} selectedProjectId="p1" onSelectProject={onSelectProject} onProjectCreated={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Notifications" }));

  expect(onSelectProject).toHaveBeenCalledWith("p2");
});

test("creates a project and calls onProjectCreated with it", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const newProject = { id: "p3", name: "New Project", created_at: "2026-08-07T00:00:00Z" };
  createProject.mockResolvedValue(newProject);

  render(<ProjectSidebar projects={projects} selectedProjectId="p1" onSelectProject={jest.fn()} onProjectCreated={onProjectCreated} />);

  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(onProjectCreated).toHaveBeenCalledWith(newProject));
});

test("clears the input after successfully creating a project", async () => {
  const user = userEvent.setup();
  createProject.mockResolvedValue({ id: "p3", name: "New Project", created_at: "2026-08-07T00:00:00Z" });

  render(<ProjectSidebar projects={projects} selectedProjectId="p1" onSelectProject={jest.fn()} onProjectCreated={jest.fn()} />);

  const input = screen.getByLabelText(/project name/i);
  await user.type(input, "New Project");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(input).toHaveValue(""));
});

test("shows an error message when creation fails", async () => {
  const user = userEvent.setup();
  createProject.mockRejectedValue({ response: { data: { detail: "A project with this name already exists" } } });

  render(<ProjectSidebar projects={projects} selectedProjectId="p1" onSelectProject={jest.fn()} onProjectCreated={jest.fn()} />);

  await user.type(screen.getByLabelText(/project name/i), "Payments Service");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(await screen.findByText("A project with this name already exists")).toBeInTheDocument();
});

test("shows an empty state when there are no projects", () => {
  render(<ProjectSidebar projects={[]} selectedProjectId={null} onSelectProject={jest.fn()} onProjectCreated={jest.fn()} />);

  expect(screen.getByText(/no projects yet/i)).toBeInTheDocument();
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectsPage from "./ProjectsPage";
import { getProjects, createProject } from "../services/api";

jest.mock("../services/api");

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("lists existing projects fetched on mount", async () => {
  getProjects.mockResolvedValue([
    { id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" },
    { id: "p2", name: "Notifications", created_at: "2026-08-06T00:00:00Z" },
  ]);

  renderPage();

  expect(await screen.findByText("Payments Service")).toBeInTheDocument();
  expect(screen.getByText("Notifications")).toBeInTheDocument();
});

test("shows an empty state when there are no projects", async () => {
  getProjects.mockResolvedValue([]);

  renderPage();

  expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
});

test("creates a project and adds it to the list", async () => {
  const user = userEvent.setup();
  getProjects.mockResolvedValue([]);
  createProject.mockResolvedValue({ id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" });

  renderPage();
  await screen.findByText(/no projects yet/i);

  await user.type(screen.getByLabelText(/project name/i), "Payments Service");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(createProject).toHaveBeenCalledWith("Payments Service"));
  expect(await screen.findByText("Payments Service")).toBeInTheDocument();
});

test("clears the input after successfully creating a project", async () => {
  const user = userEvent.setup();
  getProjects.mockResolvedValue([]);
  createProject.mockResolvedValue({ id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" });

  renderPage();
  await screen.findByText(/no projects yet/i);

  const input = screen.getByLabelText(/project name/i);
  await user.type(input, "Payments Service");
  await user.click(screen.getByRole("button", { name: /create/i }));

  await waitFor(() => expect(input).toHaveValue(""));
});

test("disables Create until a name is entered", async () => {
  getProjects.mockResolvedValue([]);
  renderPage();
  await screen.findByText(/no projects yet/i);

  expect(screen.getByRole("button", { name: /create/i })).toBeDisabled();
});

test("shows an error message when creation fails", async () => {
  const user = userEvent.setup();
  getProjects.mockResolvedValue([]);
  createProject.mockRejectedValue({ response: { data: { detail: "A project with this name already exists" } } });

  renderPage();
  await screen.findByText(/no projects yet/i);

  await user.type(screen.getByLabelText(/project name/i), "Payments Service");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(await screen.findByText("A project with this name already exists")).toBeInTheDocument();
});

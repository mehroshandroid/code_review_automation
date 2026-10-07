import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProjectsPage from "./ProjectsPage";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getProjects, createProject, updateProject, getProjectManagers, setProjectManagers, deleteProject, setProjectPlatforms } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getProjects: jest.fn(), createProject: jest.fn(), updateProject: jest.fn(),
  getProjectManagers: jest.fn(), setProjectManagers: jest.fn(), deleteProject: jest.fn(), setProjectPlatforms: jest.fn(),
}));

const projects = [
  { id: "p1", name: "Alpha", created_at: "2026-01-01T00:00:00Z", review_count: 3, manager_ids: ["pm1"], platforms: ["Android", "iOS"] },
  { id: "p2", name: "Beta", created_at: "2026-02-01T00:00:00Z", review_count: 0, manager_ids: [], platforms: [] },
];
const managers = [{ id: "pm1", email: "pat@example.com", name: "Pat" }, { id: "pm2", email: "sam@example.com", name: null }];

beforeEach(() => {
  jest.resetAllMocks();
  getProjects.mockResolvedValue(projects);
  getProjectManagers.mockResolvedValue(managers);
});

function renderAs(role) {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><ProjectsPage /></MemoryRouter>
    </AuthContext.Provider>
  );
}

function row(name) {
  return screen.getByRole("row", { name: new RegExp(name) });
}

test("lists projects with PM chips and review counts", async () => {
  renderAs("coordinator");
  await screen.findByText("Alpha");
  expect(within(row("Alpha")).getByText("Pat")).toBeInTheDocument();
  expect(within(row("Alpha")).getByText("3")).toBeInTheDocument();
});

test("coordinator does not see Delete", async () => {
  renderAs("coordinator");
  await screen.findByText("Alpha");
  expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
});

test("delete is disabled when a project has reviews", async () => {
  renderAs("management");
  await screen.findByText("Alpha");
  expect(within(row("Alpha")).getByRole("button", { name: "Delete Alpha" })).toBeDisabled();
  expect(within(row("Alpha")).getByRole("button", { name: "Delete Alpha" })).toHaveAttribute("title", "Has 3 reviews — can't be deleted");
});

test("deleting an empty project after confirmation", async () => {
  const user = userEvent.setup();
  deleteProject.mockResolvedValue();
  renderAs("admin");
  await screen.findByText("Beta");
  await user.click(within(row("Beta")).getByRole("button", { name: "Delete Beta" }));
  await user.click(screen.getByRole("button", { name: "Delete project" }));
  await waitFor(() => expect(deleteProject).toHaveBeenCalledWith("p2"));
  await waitFor(() => expect(screen.queryByText("Beta")).not.toBeInTheDocument());
});

test("creating a project", async () => {
  const user = userEvent.setup();
  createProject.mockResolvedValue({ id: "p3", name: "Gamma", created_at: "2026-03-01T00:00:00Z", review_count: 0, manager_ids: [] });
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.click(screen.getByRole("button", { name: "New project" }));
  await user.type(screen.getByLabelText("Project name"), "Gamma");
  await user.click(screen.getByRole("button", { name: "Create" }));
  expect(await screen.findByText("Gamma")).toBeInTheDocument();
});

test("renaming a project", async () => {
  const user = userEvent.setup();
  updateProject.mockResolvedValue({ ...projects[1], name: "Beta 2" });
  renderAs("coordinator");
  await screen.findByText("Beta");
  await user.click(within(row("Beta")).getByRole("button", { name: "Edit Beta" }));
  const input = screen.getByLabelText("Project name");
  await user.clear(input);
  await user.type(input, "Beta 2");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Beta 2")).toBeInTheDocument();
});

test("assigning PMs saves the selected ids", async () => {
  const user = userEvent.setup();
  setProjectManagers.mockResolvedValue({ ...projects[1], manager_ids: ["pm2"] });
  renderAs("coordinator");
  await screen.findByText("Beta");
  await user.click(within(row("Beta")).getByRole("button", { name: "Assign PMs for Beta" }));
  await user.click(screen.getByRole("button", { name: "Project managers" }));
  await user.click(screen.getByRole("checkbox", { name: "sam@example.com" }));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(setProjectManagers).toHaveBeenCalledWith("p2", ["pm2"]));
  expect(await within(row("Beta")).findByText("sam@example.com")).toBeInTheDocument();
});

test("search filters the table", async () => {
  const user = userEvent.setup();
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.type(screen.getByRole("searchbox", { name: "Search projects" }), "bet");
  expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  expect(screen.getByText("Beta")).toBeInTheDocument();
});

test("shows each project's platforms", async () => {
  renderAs("coordinator");
  await screen.findByText("Alpha");
  expect(within(row("Alpha")).getByText("Android")).toBeInTheDocument();
  expect(within(row("Alpha")).getByText("iOS")).toBeInTheDocument();
});

test("creating a project saves its platforms", async () => {
  const user = userEvent.setup();
  createProject.mockResolvedValue({ id: "p3", name: "Gamma", created_at: "2026-03-01T00:00:00Z", review_count: 0, manager_ids: [], platforms: [] });
  setProjectPlatforms.mockResolvedValue({ id: "p3", name: "Gamma", created_at: "2026-03-01T00:00:00Z", review_count: 0, platforms: ["Android", ".NET"] });
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.click(screen.getByRole("button", { name: "New project" }));
  await user.type(screen.getByLabelText("Project name"), "Gamma");
  await user.click(screen.getByRole("checkbox", { name: "Android" }));
  await user.click(screen.getByRole("checkbox", { name: ".NET" }));
  await user.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => expect(setProjectPlatforms).toHaveBeenCalledWith("p3", ["Android", ".NET"]));
  expect(await within(row("Gamma")).findByText(".NET")).toBeInTheDocument();
});

test("editing a project pre-checks and saves platforms", async () => {
  const user = userEvent.setup();
  updateProject.mockResolvedValue({ ...projects[0] });
  setProjectPlatforms.mockResolvedValue({ ...projects[0], platforms: ["Android"] });
  renderAs("coordinator");
  await screen.findByText("Alpha");
  await user.click(within(row("Alpha")).getByRole("button", { name: "Edit Alpha" }));
  expect(screen.getByRole("checkbox", { name: "iOS" })).toBeChecked();
  await user.click(screen.getByRole("checkbox", { name: "iOS" }));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(setProjectPlatforms).toHaveBeenCalledWith("p1", ["Android"]));
});

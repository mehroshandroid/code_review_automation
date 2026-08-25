import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardFilters from "./DashboardFilters";
import { createProject, updateProject } from "../services/api";

jest.mock("../services/api");

const projects = [
  { id: "p1", name: "Payments Service" },
  { id: "p2", name: "Notifications" },
];

function renderFilters(overrides = {}) {
  return render(
    <DashboardFilters
      year={2026} years={[2025, 2026]} onYearChange={jest.fn()}
      platform={null} onPlatformChange={jest.fn()}
      projectId={null} projects={projects} onProjectChange={jest.fn()} onProjectCreated={jest.fn()} onProjectRenamed={jest.fn()}
      onReset={jest.fn()}
      {...overrides}
    />
  );
}

test("shows the current year, All platforms, and All projects by default", () => {
  renderFilters();
  expect(screen.getByRole("button", { name: "Year" })).toHaveTextContent("2026");
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("All platforms");
  expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("All projects");
});

test("selecting a year calls onYearChange", async () => {
  const user = userEvent.setup();
  const onYearChange = jest.fn();
  renderFilters({ onYearChange });

  await user.click(screen.getByRole("button", { name: "Year" }));
  await user.click(screen.getByRole("button", { name: "2025" }));

  expect(onYearChange).toHaveBeenCalledWith(2025);
});

test("selecting a platform calls onPlatformChange with the platform label", async () => {
  const user = userEvent.setup();
  const onPlatformChange = jest.fn();
  renderFilters({ onPlatformChange });

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(onPlatformChange).toHaveBeenCalledWith("Android");
});

test("selecting a project calls onProjectChange with its id", async () => {
  const user = userEvent.setup();
  const onProjectChange = jest.fn();
  renderFilters({ onProjectChange });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));

  expect(onProjectChange).toHaveBeenCalledWith("p1");
});

test("clicking Reset filters calls onReset", async () => {
  const user = userEvent.setup();
  const onReset = jest.fn();
  renderFilters({ onReset });

  await user.click(screen.getByRole("button", { name: /reset filters/i }));

  expect(onReset).toHaveBeenCalled();
});

test("creating a new project via the Project dropdown calls onProjectCreated and selects it", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const onProjectChange = jest.fn();
  const newProject = { id: "p3", name: "New Project" };
  createProject.mockResolvedValue(newProject);
  renderFilters({ onProjectCreated, onProjectChange });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: /add new project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  expect(createProject).toHaveBeenCalledWith("New Project");
  expect(onProjectCreated).toHaveBeenCalledWith(newProject);
  expect(onProjectChange).toHaveBeenCalledWith("p3");
});

test("does not show a rename button when 'All projects' is selected", () => {
  renderFilters({ projectId: null });
  expect(screen.queryByRole("button", { name: /rename/i })).not.toBeInTheDocument();
});

test("shows a rename button when a specific project is selected, pre-filled with its current name", async () => {
  const user = userEvent.setup();
  renderFilters({ projectId: "p1" });

  await user.click(screen.getByRole("button", { name: /rename/i }));

  expect(screen.getByLabelText(/project name/i)).toHaveValue("Payments Service");
});

test("renaming the selected project calls updateProject and onProjectRenamed", async () => {
  const user = userEvent.setup();
  const onProjectRenamed = jest.fn();
  const updated = { id: "p1", name: "Payments Team" };
  updateProject.mockResolvedValue(updated);
  renderFilters({ projectId: "p1", onProjectRenamed });

  await user.click(screen.getByRole("button", { name: /rename/i }));
  await user.clear(screen.getByLabelText(/project name/i));
  await user.type(screen.getByLabelText(/project name/i), "Payments Team");
  await user.click(screen.getByRole("button", { name: /save/i }));

  expect(updateProject).toHaveBeenCalledWith("p1", "Payments Team");
  expect(onProjectRenamed).toHaveBeenCalledWith(updated);
});

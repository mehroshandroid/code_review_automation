import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BulkInitiateDialog from "./BulkInitiateDialog";
import { bulkInitiate, getBulkPreview, getProjectManagers, getReviewers, setProjectManagers } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"), getReviewers: jest.fn(), getBulkPreview: jest.fn(), bulkInitiate: jest.fn(),
  getProjectManagers: jest.fn(), setProjectManagers: jest.fn(),
}));

const preview = {
  year: 2026, quarter: 4,
  eligible: [
    { project_id: "p1", project_name: "Alpha", platforms: ["Android", "iOS"], managers: [{ id: "pm", name: "Pat" }],
      suggested_reviewers: { Android: "r1", iOS: null } },
    { project_id: "p2", project_name: "Beta", platforms: ["Android"], managers: [], suggested_reviewers: { Android: null } },
  ],
  skipped: [{ project_id: "p3", project_name: "Gamma", reason: "Already initiated" }],
};

beforeEach(() => {
  jest.resetAllMocks();
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }, { id: "r2", email: "sam@example.com", name: "Sam" }]);
  getBulkPreview.mockResolvedValue(preview);
  getProjectManagers.mockResolvedValue([{ id: "pm", name: "Pat", email: "pat@example.com" }, { id: "pm2", name: null, email: "quinn@example.com" }]);
});

function renderDialog(props = {}) {
  return render(<BulkInitiateDialog year={2026} quarters={[3, 4]} canAssignPm onDone={jest.fn()} onClose={jest.fn()} {...props} />);
}

test("loads the current quarter's preview with pre-filled reviewers, PMs and skipped projects", async () => {
  renderDialog();
  const alpha = await screen.findByRole("row", { name: /Alpha/ });
  expect(getBulkPreview).toHaveBeenCalledWith(2026, 4);
  await within(alpha).findAllByRole("option", { name: "Rae" });
  expect(within(alpha).getByLabelText("Alpha reviewer for Android")).toHaveValue("r1");
  expect(within(alpha).getByLabelText("Alpha reviewer for iOS")).toHaveValue("");
  expect(within(alpha).getByText("Pat")).toBeInTheDocument();
  expect(within(screen.getByRole("row", { name: /Beta/ })).getByText(/No PM assigned/)).toBeInTheDocument();
  expect(screen.getByText("Gamma")).toBeInTheDocument();
  expect(screen.getByText("Already initiated")).toBeInTheDocument();
});

test("changing the quarter reloads the preview", async () => {
  const user = userEvent.setup();
  renderDialog();
  await screen.findByRole("row", { name: /Alpha/ });
  await user.selectOptions(screen.getByLabelText("Quarter"), "3");
  await waitFor(() => expect(getBulkPreview).toHaveBeenLastCalledWith(2026, 3));
});

test("Set for all fills only empty slots", async () => {
  const user = userEvent.setup();
  renderDialog();
  await screen.findAllByRole("option", { name: "Sam" });
  await user.selectOptions(screen.getByLabelText("Set all Android reviewers"), "r2");
  expect(screen.getByLabelText("Alpha reviewer for Android")).toHaveValue("r1");
  expect(screen.getByLabelText("Beta reviewer for Android")).toHaveValue("r2");
  expect(screen.getByLabelText("Alpha reviewer for iOS")).toHaveValue("");
});

test("posts only filled slots and leaves empty platforms for later", async () => {
  const user = userEvent.setup();
  bulkInitiate.mockResolvedValue({ results: [
    { project_id: "p1", project_name: "Alpha", status: "started", reason: null },
  ] });
  renderDialog();
  await screen.findAllByRole("option", { name: "Sam" });
  // Alpha has Android pre-filled; Beta has nothing filled, so it isn't counted.
  expect(within(screen.getByRole("row", { name: /Alpha/ })).getByText("iOS left for later")).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "Initiate 1 project" });
  expect(submit).toBeEnabled();
  await user.click(submit);
  await waitFor(() => expect(bulkInitiate).toHaveBeenCalledWith({
    year: 2026, quarter: 4,
    projects: [{ project_id: "p1", assignments: [{ platform: "Android", reviewer_id: "r1" }] }],
  }));
});

test("unticked projects aren't sent", async () => {
  const user = userEvent.setup();
  renderDialog();
  await screen.findAllByRole("option", { name: "Sam" });
  await user.click(screen.getByLabelText("Include Alpha"));
  expect(screen.getByRole("button", { name: "Initiate 0 projects" })).toBeDisabled();
});

test("shows the results summary and reloads the dashboard on Done", async () => {
  const user = userEvent.setup();
  const onDone = jest.fn();
  bulkInitiate.mockResolvedValue({ results: [
    { project_id: "p1", project_name: "Alpha", status: "started", reason: null },
    { project_id: "p2", project_name: "Beta", status: "skipped", reason: "This quarter's review has already been initiated." },
  ] });
  renderDialog({ onDone });
  await screen.findAllByRole("option", { name: "Sam" });
  await user.selectOptions(screen.getByLabelText("Set all Android reviewers"), "r2");
  await user.selectOptions(screen.getByLabelText("Alpha reviewer for iOS"), "r2");
  await user.click(screen.getByRole("button", { name: "Initiate 2 projects" }));
  expect(await screen.findByText("Started 1 of 2 projects.")).toBeInTheDocument();
  expect(screen.getByText(/Beta: This quarter's review has already been initiated\./)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Done" }));
  expect(onDone).toHaveBeenCalled();
});

test("says so when nothing is eligible", async () => {
  getBulkPreview.mockResolvedValue({ ...preview, eligible: [] });
  renderDialog();
  expect(await screen.findByText("No projects can be initiated for this quarter.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Initiate 0 projects" })).toBeDisabled();
});

test("clicking outside while initiating doesn't close the dialog", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  bulkInitiate.mockReturnValue(new Promise(() => {}));
  const { container } = renderDialog({ onClose });
  await screen.findAllByRole("option", { name: "Sam" });
  await user.click(screen.getByRole("button", { name: "Initiate 1 project" }));
  await screen.findByRole("button", { name: "Initiating…" });
  await user.click(container.querySelector(".dialog-backdrop"));
  expect(onClose).not.toHaveBeenCalled();
});

test("a failed submit shows the error and reloads the dashboard, since some projects may have started", async () => {
  const user = userEvent.setup();
  const onDone = jest.fn();
  bulkInitiate.mockRejectedValue({ response: { data: { detail: "Server error" } } });
  renderDialog({ onDone });
  await screen.findAllByRole("option", { name: "Sam" });
  await user.click(screen.getByRole("button", { name: "Initiate 1 project" }));
  expect(await screen.findByText("Server error")).toBeInTheDocument();
  expect(onDone).toHaveBeenCalled();
});

test("a project without a PM can get one from the dialog, and the row shows it", async () => {
  const user = userEvent.setup();
  setProjectManagers.mockResolvedValue({ id: "p2", name: "Beta", manager_ids: ["pm2"] });
  renderDialog();
  const beta = await screen.findByRole("row", { name: /Beta/ });
  await user.click(within(beta).getByRole("button", { name: "Assign PM for Beta" }));
  await user.click(await screen.findByRole("button", { name: "Project managers" }));
  await user.click(screen.getByRole("checkbox", { name: "quinn@example.com" }));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(setProjectManagers).toHaveBeenCalledWith("p2", ["pm2"]));
  const updated = screen.getByRole("row", { name: /Beta/ });
  expect(within(updated).getByText("quinn@example.com")).toBeInTheDocument();
  expect(within(updated).queryByText(/No PM assigned/)).not.toBeInTheDocument();
  // The bulk dialog stays open with its choices intact.
  expect(screen.getByLabelText("Alpha reviewer for Android")).toHaveValue("r1");
});

test("existing PMs can be changed from the dialog", async () => {
  const user = userEvent.setup();
  renderDialog();
  const alpha = await screen.findByRole("row", { name: /Alpha/ });
  await user.click(within(alpha).getByRole("button", { name: "Edit PMs for Alpha" }));
  await user.click(await screen.findByRole("button", { name: "Project managers" }));
  expect(screen.getByRole("checkbox", { name: "Pat" })).toBeChecked();
});

test("PM assignment isn't offered without the permission", async () => {
  renderDialog({ canAssignPm: false });
  const beta = await screen.findByRole("row", { name: /Beta/ });
  expect(within(beta).queryByRole("button", { name: "Assign PM for Beta" })).not.toBeInTheDocument();
});

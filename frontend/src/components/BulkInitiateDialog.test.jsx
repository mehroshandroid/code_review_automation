import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BulkInitiateDialog from "./BulkInitiateDialog";
import { bulkInitiate, getBulkPreview, getReviewers } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"), getReviewers: jest.fn(), getBulkPreview: jest.fn(), bulkInitiate: jest.fn(),
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
});

function renderDialog(props = {}) {
  return render(<BulkInitiateDialog year={2026} quarters={[3, 4]} onDone={jest.fn()} onClose={jest.fn()} {...props} />);
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

test("Initiate stays disabled until every ticked project is complete, then posts the body", async () => {
  const user = userEvent.setup();
  bulkInitiate.mockResolvedValue({ results: [
    { project_id: "p1", project_name: "Alpha", status: "started", reason: null },
  ] });
  renderDialog();
  await screen.findAllByRole("option", { name: "Sam" });
  const submit = screen.getByRole("button", { name: "Initiate 2 projects" });
  expect(submit).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Alpha reviewer for iOS"), "r2");
  expect(submit).toBeDisabled();
  await user.click(screen.getByLabelText("Include Beta"));
  const one = screen.getByRole("button", { name: "Initiate 1 project" });
  expect(one).toBeEnabled();
  await user.click(one);
  await waitFor(() => expect(bulkInitiate).toHaveBeenCalledWith({
    year: 2026, quarter: 4,
    projects: [{ project_id: "p1", assignments: [{ platform: "Android", reviewer_id: "r1" }, { platform: "iOS", reviewer_id: "r2" }] }],
  }));
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

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadReviewDialog from "./UploadReviewDialog";
import { uploadCompletedReview, createProject } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  uploadCompletedReview: jest.fn(),
  createProject: jest.fn(),
}));

const projects = [{ id: "p1", name: "Payments Service" }];

function renderDialog(overrides = {}) {
  return render(
    <UploadReviewDialog projects={projects} onProjectCreated={jest.fn()} onUploaded={jest.fn()} onClose={jest.fn()} {...overrides} />
  );
}

async function selectProject(user) {
  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "Payments Service" }));
}

test("platform cards are disabled until a project is chosen", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(uploadCompletedReview).not.toHaveBeenCalled();
});

test("selecting a project, a platform, then a file uploads it, calls onUploaded, and shows a success message without auto-closing", async () => {
  const user = userEvent.setup();
  const onUploaded = jest.fn();
  const onClose = jest.fn();
  const uploadedReview = { id: "r1", project_name: "Payments Service", platform: "Android", created_at: "2026-06-15T00:00:00Z" };
  uploadCompletedReview.mockResolvedValue(uploadedReview);
  renderDialog({ onUploaded, onClose });

  await selectProject(user);
  await user.click(screen.getByRole("button", { name: "Android" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  await waitFor(() => expect(uploadCompletedReview).toHaveBeenCalledWith({ projectId: "p1", platform: "Android", file }));
  await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(uploadedReview));
  expect(await screen.findByText(/uploaded successfully/i)).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: /done/i }));
  expect(onClose).toHaveBeenCalled();
});

test("shows the backend's error message and keeps the dialog open on failure", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  uploadCompletedReview.mockRejectedValue({ response: { data: { detail: "Sheet is missing a reviewer name." } } });
  renderDialog({ onClose });

  await selectProject(user);
  await user.click(screen.getByRole("button", { name: "iOS" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  expect(await screen.findByText("Sheet is missing a reviewer name.")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});

test("creating a project via the dialog selects it for the upload", async () => {
  const user = userEvent.setup();
  const onProjectCreated = jest.fn();
  const newProject = { id: "p2", name: "New Project" };
  createProject.mockResolvedValue(newProject);
  uploadCompletedReview.mockResolvedValue({ id: "r1", project_name: "New Project", platform: ".NET", created_at: "2026-06-15T00:00:00Z" });
  renderDialog({ onProjectCreated });

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: /add new project/i }));
  await user.type(screen.getByLabelText(/project name/i), "New Project");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  expect(onProjectCreated).toHaveBeenCalledWith(newProject);
  await user.click(screen.getByRole("button", { name: ".NET" }));
  const file = new File(["dummy"], "review.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await user.upload(screen.getByLabelText(/choose review sheet/i), file);

  await waitFor(() => expect(uploadCompletedReview).toHaveBeenCalledWith({ projectId: "p2", platform: ".NET", file }));
});

test("clicking Cancel calls onClose", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  renderDialog({ onClose });

  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(onClose).toHaveBeenCalled();
});

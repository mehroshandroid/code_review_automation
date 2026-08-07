import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";
import { getCompileCheckMode } from "../services/compileCheckModeStorage";
import { getSampleTemplates } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getSampleTemplates: jest.fn(),
}));

beforeEach(() => {
  localStorage.clear();
  getSampleTemplates.mockReset();
  getSampleTemplates.mockResolvedValue([]);
});

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

test("calls onSubmit with both files when extensions are valid", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: xlsx, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
  });
});

test("shows a validation error and does not call onSubmit when the zip has the wrong extension", async () => {
  // applyAccept: false — a mismatched-extension file is still selectable in
  // real browsers (the `accept` attribute is only an advisory filter on the
  // native picker), so this exercises our own extension check rather than
  // user-event's stricter simulated filtering.
  const user = userEvent.setup({ applyAccept: false });
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const notAZip = buildFile("project.txt", "text/plain");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), notAZip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByText(/must be a \.zip file/i)).toBeInTheDocument();
});

test("disables the start button until both files are chosen", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  expect(screen.getByRole("button", { name: /start review/i })).toBeEnabled();
});

test("disables inputs and shows the starting label when disabled prop is true", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={true} />);
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: /starting review/i })).toBeDisabled();
});

test("shows a custom disabledLabel on the button when disabled and provided", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={true} disabledLabel="Coming soon" />);
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("does not render the compile-check toggle by default", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  expect(screen.queryByText("Compile-time lint")).not.toBeInTheDocument();
});

test("renders the compile-check toggle when showCompileCheckToggle is true, defaulting to Compile-time lint (Docker) for Android", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle />);
  expect(screen.getByRole("button", { name: "Compile-time lint (Docker)" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Compile-time lint (local)" })).not.toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Static file analysis" })).not.toHaveClass("btn-primary");
});

test("selecting Compile-time lint (local) persists the choice and highlights it", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle />);

  await user.click(screen.getByRole("button", { name: "Compile-time lint (local)" }));

  expect(screen.getByRole("button", { name: "Compile-time lint (local)" })).toHaveClass("btn-primary");
  expect(getCompileCheckMode()).toBe("local");
});

test("does not show the local build option, or the (Docker) suffix, for a non-Android platform", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle platformLabel="iOS" />);
  expect(screen.getByRole("button", { name: "Compile-time lint" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Compile-time lint (Docker)" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Compile-time lint (local)" })).not.toBeInTheDocument();
});

test("shows the (Docker) suffix but not the local build option for .NET", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle platformLabel=".NET" />);
  expect(screen.getByRole("button", { name: "Compile-time lint (Docker)" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Compile-time lint (local)" })).not.toBeInTheDocument();
});

test("selecting Static file analysis persists the choice and highlights it", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle />);

  await user.click(screen.getByRole("button", { name: "Static file analysis" }));

  expect(screen.getByRole("button", { name: "Static file analysis" })).toHaveClass("btn-primary");
  expect(getCompileCheckMode()).toBe("static");
});

test("defaults to upload mode with the zip picker visible and DevOps fields hidden", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/repo url/i)).not.toBeInTheDocument();
});

test("switching to Clone from Azure DevOps hides the zip picker and shows the DevOps fields", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));

  expect(screen.queryByLabelText(/android project/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/repo url/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/personal access token/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/branch/i)).toBeInTheDocument();
});

test("the Personal Access Token field is type=password", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));
  expect(screen.getByLabelText(/personal access token/i)).toHaveAttribute("type", "password");
});

test("disables the start button until repo URL, PAT, and template are all provided in DevOps mode", async () => {
  const user = userEvent.setup();
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));

  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  await user.type(screen.getByLabelText(/repo url/i), "https://dev.azure.com/myorg/MyProject/_git/my-repo");
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  await user.type(screen.getByLabelText(/personal access token/i), "fake-pat");
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();

  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  expect(screen.getByRole("button", { name: /start review/i })).toBeEnabled();
});

test("defaults the zip picker label to Android when no platformLabel is given", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("uses the given platformLabel for the zip picker label", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} platformLabel="iOS" />);
  expect(screen.getByLabelText(/ios project/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/android project/i)).not.toBeInTheDocument();
});

test("calls onSubmit with the DevOps fields (and a null androidZip) in DevOps mode", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);
  await user.click(screen.getByRole("button", { name: /clone from azure devops/i }));

  await user.type(screen.getByLabelText(/repo url/i), "https://dev.azure.com/myorg/MyProject/_git/my-repo");
  await user.type(screen.getByLabelText(/personal access token/i), "fake-pat");
  await user.type(screen.getByLabelText(/branch/i), "release/1.0");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: null,
    excelTemplate: xlsx,
    devopsRepoUrl: "https://dev.azure.com/myorg/MyProject/_git/my-repo",
    devopsPat: "fake-pat",
    devopsBranch: "release/1.0",
  });
});

test("shows 'Using default' and hides the file picker when a sample template is configured for the platform", async () => {
  getSampleTemplates.mockResolvedValue([
    { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
  ]);
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  expect(await screen.findByText(/using default: android-default\.xlsx/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/scoring template/i)).not.toBeInTheDocument();
});

test("does not show 'Using default' when no sample template is configured for the platform", async () => {
  getSampleTemplates.mockResolvedValue([
    { platform: "iOS", filename: "ios-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
  ]);
  render(<UploadForm onSubmit={jest.fn()} disabled={false} platformLabel="Android" />);

  await screen.findByLabelText(/scoring template/i);
  expect(screen.queryByText(/using default/i)).not.toBeInTheDocument();
});

test("start review is enabled without choosing a template file when a default is configured", async () => {
  const user = userEvent.setup();
  getSampleTemplates.mockResolvedValue([
    { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
  ]);
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  await screen.findByText(/using default: android-default\.xlsx/i);
  const zip = buildFile("project.zip", "application/zip");
  await user.upload(screen.getByLabelText(/android project/i), zip);

  expect(screen.getByRole("button", { name: /start review/i })).toBeEnabled();
});

test("submits with excelTemplate: null when the default template is used", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  getSampleTemplates.mockResolvedValue([
    { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
  ]);
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  await screen.findByText(/using default: android-default\.xlsx/i);
  const zip = buildFile("project.zip", "application/zip");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    androidZip: zip, excelTemplate: null, devopsRepoUrl: null, devopsPat: null, devopsBranch: null,
  });
});

test("'Choose a different file' reveals the normal file picker and requires a file to start", async () => {
  const user = userEvent.setup();
  getSampleTemplates.mockResolvedValue([
    { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
  ]);
  render(<UploadForm onSubmit={jest.fn()} disabled={false} />);

  await screen.findByText(/using default: android-default\.xlsx/i);
  const zip = buildFile("project.zip", "application/zip");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.click(screen.getByRole("button", { name: /choose a different file/i }));

  expect(screen.queryByText(/using default/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/scoring template/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /start review/i })).toBeDisabled();
});

test("'Use default instead' reverts back to the default after choosing a different file", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  getSampleTemplates.mockResolvedValue([
    { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
  ]);
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  await screen.findByText(/using default: android-default\.xlsx/i);
  await user.click(screen.getByRole("button", { name: /choose a different file/i }));
  await user.click(screen.getByRole("button", { name: /use default instead/i }));

  expect(await screen.findByText(/using default: android-default\.xlsx/i)).toBeInTheDocument();

  const zip = buildFile("project.zip", "application/zip");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ excelTemplate: null }));
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";
import { getCompileCheckMode } from "../services/compileCheckModeStorage";

beforeEach(() => {
  localStorage.clear();
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

test("renders the compile-check toggle when showCompileCheckToggle is true, defaulting to Compile-time lint", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={false} showCompileCheckToggle />);
  expect(screen.getByRole("button", { name: "Compile-time lint" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Static file analysis" })).not.toHaveClass("btn-primary");
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

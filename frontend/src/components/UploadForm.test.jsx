import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";

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

  expect(onSubmit).toHaveBeenCalledWith(zip, xlsx);
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

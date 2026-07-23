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
  await user.upload(screen.getByLabelText(/review template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith(zip, xlsx);
});

test("shows a validation error and does not call onSubmit when the zip has the wrong extension", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const notAZip = buildFile("project.txt", "text/plain");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), notAZip);
  await user.upload(screen.getByLabelText(/review template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByText(/must be a \.zip file/i)).toBeInTheDocument();
});

test("disables inputs and button when disabled prop is true", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={true} />);
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button")).toBeDisabled();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectDialog from "./ProjectDialog";

test("submitting calls onSubmit with the trimmed name, then onClose", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn().mockResolvedValue(undefined);
  const onClose = jest.fn();
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={onSubmit} onClose={onClose} />);

  await user.type(screen.getByLabelText(/project name/i), "  Payments  ");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(onSubmit).toHaveBeenCalledWith("Payments");
  expect(onClose).toHaveBeenCalled();
});

test("pre-fills the name field from initialName", () => {
  render(<ProjectDialog title="Rename project" initialName="Old Name" submitLabel="Save" onSubmit={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByLabelText(/project name/i)).toHaveValue("Old Name");
});

test("shows an error message and does not close when onSubmit rejects", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn().mockRejectedValue({ response: { data: { detail: "A project with this name already exists" } } });
  const onClose = jest.fn();
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={onSubmit} onClose={onClose} />);

  await user.type(screen.getByLabelText(/project name/i), "Payments");
  await user.click(screen.getByRole("button", { name: /create/i }));

  expect(await screen.findByText("A project with this name already exists")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});

test("clicking Cancel calls onClose without submitting", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  const onClose = jest.fn();
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={onSubmit} onClose={onClose} />);

  await user.click(screen.getByRole("button", { name: /cancel/i }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(onClose).toHaveBeenCalled();
});

test("the submit button is disabled when the name is empty", () => {
  render(<ProjectDialog title="New project" initialName="" submitLabel="Create" onSubmit={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByRole("button", { name: /create/i })).toBeDisabled();
});

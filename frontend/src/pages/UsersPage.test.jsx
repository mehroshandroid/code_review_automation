import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import UsersPage from "./UsersPage";
import { listUsers, createUser, updateUser, deleteUser, getProjects } from "../services/api";
import { AuthContext } from "../context/AuthContext";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  listUsers: jest.fn(),
  createUser: jest.fn(),
  updateUser: jest.fn(),
  deleteUser: jest.fn(),
  getProjects: jest.fn(),
}));

const users = [
  { id: "u1", email: "admin@example.com", name: "Ada Admin", role: "admin", is_active: true },
  { id: "u2", email: "reviewer@example.com", name: null, role: "reviewer", is_active: true },
  { id: "u3", email: "pm@example.com", name: null, role: "project_manager", is_active: true, project_ids: ["p1"] },
];

beforeEach(() => {
  jest.resetAllMocks();
  listUsers.mockResolvedValue(users);
  getProjects.mockResolvedValue([{ id: "p1", name: "Alpha" }]);
});

function renderPage() {
  return render(<MemoryRouter><UsersPage /></MemoryRouter>);
}

test("lists existing users with their role and status", async () => {
  renderPage();

  expect(await screen.findByText("admin@example.com")).toBeInTheDocument();
  expect(screen.getByText("reviewer@example.com")).toBeInTheDocument();
});

test("creating a new user calls createUser and refreshes the list", async () => {
  const user = userEvent.setup();
  createUser.mockResolvedValue({ id: "u9", email: "new@example.com", role: "coordinator", is_active: true });
  renderPage();
  await screen.findByText("admin@example.com");

  await user.click(screen.getByRole("button", { name: /add user/i }));
  const dialog = screen.getByText("New user").closest(".dialog");
  await user.type(within(dialog).getByLabelText(/^name$/i), "Nia");
  await user.type(within(dialog).getByLabelText(/email/i), "new@example.com");
  await user.type(within(dialog).getByLabelText(/password/i), "correct horse");
  await user.selectOptions(within(dialog).getByLabelText(/role/i), "coordinator");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  await waitFor(() => expect(createUser).toHaveBeenCalledWith("new@example.com", "correct horse", "coordinator", "Nia"));
  await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2));
});

test("changing a user's role calls updateUser", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue({ ...users[1], role: "management" });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.selectOptions(screen.getByLabelText(/role for reviewer@example\.com/i), "management");

  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { role: "management" }));
});

test("deactivating a user calls updateUser with isActive false", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue({ ...users[1], is_active: false });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.click(screen.getByRole("button", { name: /deactivate reviewer@example\.com/i }));

  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { isActive: false }));
});

test("shows an error message instead of failing silently when a role change is rejected", async () => {
  const user = userEvent.setup();
  updateUser.mockRejectedValue({ response: { data: { detail: "You don't have permission to do this" } } });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.selectOptions(screen.getByLabelText(/role for reviewer@example\.com/i), "management");

  expect(await screen.findByText("You don't have permission to do this")).toBeInTheDocument();
});

test("shows an error message instead of failing silently when deactivating is rejected", async () => {
  const user = userEvent.setup();
  updateUser.mockRejectedValue({ response: { data: { detail: "Something went wrong" } } });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.click(screen.getByRole("button", { name: /deactivate reviewer@example\.com/i }));

  expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
});

function renderAsUser(userId) {
  const value = { user: { id: userId, email: "whoever@example.com", role: "admin" }, loading: false, login: jest.fn(), logout: jest.fn() };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter><UsersPage /></MemoryRouter>
    </AuthContext.Provider>
  );
}

test("disables the role select and hides the deactivate/delete buttons for your own row", async () => {
  renderAsUser("u1");
  await screen.findByText("admin@example.com");

  expect(screen.getByLabelText(/role for admin@example\.com/i)).toBeDisabled();
  expect(screen.queryByRole("button", { name: /deactivate admin@example\.com/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /delete admin@example\.com/i })).not.toBeInTheDocument();
  // Other rows are unaffected.
  expect(screen.getByLabelText(/role for reviewer@example\.com/i)).toBeEnabled();
  expect(screen.getByRole("button", { name: /deactivate reviewer@example\.com/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /delete reviewer@example\.com/i })).toBeInTheDocument();
});

test("setting a new password for a user calls updateUser with the password", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue(users[1]);
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.click(screen.getByRole("button", { name: /set password for reviewer@example\.com/i }));
  const dialog = screen.getByText("Set a new password").closest(".dialog");
  await user.type(within(dialog).getByLabelText(/new password/i), "a brand new password");
  await user.click(within(dialog).getByRole("button", { name: /^save$/i }));

  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { password: "a brand new password" }));
});

test("deleting a user calls deleteUser and refreshes the list", async () => {
  const user = userEvent.setup();
  deleteUser.mockResolvedValue();
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.click(screen.getByRole("button", { name: /delete reviewer@example\.com/i }));

  await waitFor(() => expect(deleteUser).toHaveBeenCalledWith("u2"));
  await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2));
});

test("shows an error message instead of failing silently when delete is rejected", async () => {
  const user = userEvent.setup();
  deleteUser.mockRejectedValue({ response: { data: { detail: "You cannot delete your own account." } } });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.click(screen.getByRole("button", { name: /delete reviewer@example\.com/i }));

  expect(await screen.findByText("You cannot delete your own account.")).toBeInTheDocument();
});


test("role dropdown offers all five roles with labels", async () => {
  renderPage();
  await screen.findByText("reviewer@example.com");
  const select = screen.getByLabelText(/role for reviewer@example\.com/i);
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(
    ["Admin", "Management", "Coordinator", "Reviewer", "Project Manager"],
  );
});

test("PM rows show assigned projects as links to the Projects page", async () => {
  renderPage();
  const chip = await screen.findByRole("link", { name: "Alpha" });
  expect(chip).toHaveAttribute("href", "/projects");
});

test("editing a name saves on blur", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue({ ...users[1], name: "Rae" });
  renderPage();
  const input = await screen.findByLabelText(/name for reviewer@example\.com/i);
  await user.type(input, "Rae");
  await user.tab();
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { name: "Rae" }));
});

test("leaving a name unchanged does not save", async () => {
  const user = userEvent.setup();
  renderPage();
  const input = await screen.findByLabelText(/name for admin@example\.com/i);
  await user.click(input);
  await user.tab();
  expect(updateUser).not.toHaveBeenCalled();
});

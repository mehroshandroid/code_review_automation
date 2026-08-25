import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import UsersPage from "./UsersPage";
import { listUsers, createUser, updateUser } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  listUsers: jest.fn(),
  createUser: jest.fn(),
  updateUser: jest.fn(),
}));

const users = [
  { id: "u1", email: "admin@example.com", role: "admin", is_active: true },
  { id: "u2", email: "reviewer@example.com", role: "reviewer", is_active: true },
];

beforeEach(() => {
  jest.resetAllMocks();
  listUsers.mockResolvedValue(users);
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
  createUser.mockResolvedValue({ id: "u3", email: "new@example.com", role: "user", is_active: true });
  renderPage();
  await screen.findByText("admin@example.com");

  await user.click(screen.getByRole("button", { name: /add user/i }));
  const dialog = screen.getByText("New user").closest(".dialog");
  await user.type(within(dialog).getByLabelText(/email/i), "new@example.com");
  await user.type(within(dialog).getByLabelText(/password/i), "correct horse");
  await user.selectOptions(within(dialog).getByLabelText(/role/i), "user");
  await user.click(screen.getByRole("button", { name: /^create$/i }));

  await waitFor(() => expect(createUser).toHaveBeenCalledWith("new@example.com", "correct horse", "user"));
  await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2));
});

test("changing a user's role calls updateUser", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue({ ...users[1], role: "user" });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.selectOptions(screen.getByLabelText(/role for reviewer@example\.com/i), "user");

  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { role: "user" }));
});

test("deactivating a user calls updateUser with isActive false", async () => {
  const user = userEvent.setup();
  updateUser.mockResolvedValue({ ...users[1], is_active: false });
  renderPage();
  await screen.findByText("reviewer@example.com");

  await user.click(screen.getByRole("button", { name: /deactivate reviewer@example\.com/i }));

  await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u2", { isActive: false }));
});

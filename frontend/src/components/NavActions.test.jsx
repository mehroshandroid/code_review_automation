import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import NavActions from "./NavActions";
import { AuthContext } from "../context/AuthContext";

function renderAs(user) {
  return render(
    <AuthContext.Provider value={{ user, loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter>
        <NavActions />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

test("renders nothing when not logged in", () => {
  const { container } = renderAs(null);
  expect(container).toBeEmptyDOMElement();
});

test("shows Settings and Users links for admin", () => {
  renderAs({ id: "u1", email: "admin@example.com", role: "admin" });

  expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /users/i })).toBeInTheDocument();
});

test("shows Settings but not Users, for reviewer", () => {
  renderAs({ id: "u1", email: "reviewer@example.com", role: "reviewer" });

  expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /users/i })).not.toBeInTheDocument();
});

test("shows neither Settings nor Users, for the user role", () => {
  renderAs({ id: "u1", email: "user@example.com", role: "user" });

  expect(screen.queryByRole("link", { name: /settings/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /users/i })).not.toBeInTheDocument();
});

test("the email and Log out are not visible until the user icon is clicked", () => {
  renderAs({ id: "u1", email: "admin@example.com", role: "admin" });

  expect(screen.queryByText("admin@example.com")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
});

test("clicking the user icon opens a popup with the email address and Log out", async () => {
  const user = userEvent.setup();
  renderAs({ id: "u1", email: "admin@example.com", role: "admin" });

  await user.click(screen.getByRole("button", { name: /user menu/i }));

  expect(screen.getByText("admin@example.com")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
});

test("Log out inside the popup calls the context's logout function", async () => {
  const user = userEvent.setup();
  const logoutFn = jest.fn();
  render(
    <AuthContext.Provider value={{ user: { id: "u1", email: "a@example.com", role: "admin" }, loading: false, login: jest.fn(), logout: logoutFn }}>
      <MemoryRouter>
        <NavActions />
      </MemoryRouter>
    </AuthContext.Provider>
  );

  await user.click(screen.getByRole("button", { name: /user menu/i }));
  await user.click(screen.getByRole("button", { name: /log out/i }));

  expect(logoutFn).toHaveBeenCalled();
});

test("clicking outside the popup closes it", async () => {
  const user = userEvent.setup();
  render(
    <div>
      <AuthContext.Provider value={{ user: { id: "u1", email: "admin@example.com", role: "admin" }, loading: false, login: jest.fn(), logout: jest.fn() }}>
        <MemoryRouter>
          <NavActions />
        </MemoryRouter>
      </AuthContext.Provider>
      <button type="button">Outside</button>
    </div>
  );

  await user.click(screen.getByRole("button", { name: /user menu/i }));
  expect(screen.getByText("admin@example.com")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Outside" }));

  expect(screen.queryByText("admin@example.com")).not.toBeInTheDocument();
});

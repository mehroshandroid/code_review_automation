import { render, screen } from "@testing-library/react";
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

test("shows Settings and Users links, plus email/role and Log out, for admin", () => {
  renderAs({ id: "u1", email: "admin@example.com", role: "admin" });

  expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /users/i })).toBeInTheDocument();
  expect(screen.getByText(/admin@example\.com/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
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

test("Log out calls the context's logout function", async () => {
  const logoutFn = jest.fn();
  render(
    <AuthContext.Provider value={{ user: { id: "u1", email: "a@example.com", role: "admin" }, loading: false, login: jest.fn(), logout: logoutFn }}>
      <MemoryRouter>
        <NavActions />
      </MemoryRouter>
    </AuthContext.Provider>
  );

  screen.getByRole("button", { name: /log out/i }).click();

  expect(logoutFn).toHaveBeenCalled();
});

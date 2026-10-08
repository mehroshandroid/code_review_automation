import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AppNav from "./AppNav";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";

function renderNav(user, path = "/", logout = jest.fn()) {
  render(
    <AuthContext.Provider value={{ user, loading: false, login: jest.fn(), logout }}>
      <MemoryRouter initialEntries={[path]}><AppNav /></MemoryRouter>
    </AuthContext.Provider>
  );
  return { logout };
}

function linkNames() {
  return screen.getAllByRole("link").map((link) => link.textContent);
}

test("brand links to the user's home", () => {
  renderNav(userWithRole("reviewer"));
  expect(screen.getByRole("link", { name: /codeassure/i })).toHaveAttribute("href", "/my-reviews");
});

test.each([
  ["admin", ["Dashboard", "Quarterly", "My reviews", "Projects", "Users", "Queue"]],
  ["management", ["Dashboard", "Quarterly", "My reviews", "Projects"]],
  ["coordinator", ["Dashboard", "Projects"]],
  ["reviewer", ["My reviews"]],
  ["project_manager", ["Dashboard"]],
])("%s sees the right links", (role, expected) => {
  renderNav(userWithRole(role));
  expect(linkNames().filter((name) => !/codeassure/i.test(name))).toEqual(expected);
});

test("marks the active link", () => {
  renderNav(userWithRole("admin"), "/projects");
  expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
});

test("avatar shows initials, name and role", () => {
  renderNav(userWithRole("management", { name: "Mehrosh Mehboob" }));
  expect(screen.getByText("MM")).toBeInTheDocument();
  expect(screen.getByText("Mehrosh Mehboob")).toBeInTheDocument();
  expect(screen.getByText("Management")).toBeInTheDocument();
});

test("account menu opens, shows permitted items, closes on Escape and returns focus", async () => {
  const user = userEvent.setup();
  renderNav(userWithRole("admin"));
  const trigger = screen.getByRole("button", { name: /account menu/i });
  expect(trigger).toHaveAttribute("aria-expanded", "false");

  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("menuitem", { name: "Settings" })).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Users" })).toBeInTheDocument();

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test("reviewer menu has no Settings or Users, and log out works", async () => {
  const user = userEvent.setup();
  const { logout } = renderNav(userWithRole("reviewer"));
  await user.click(screen.getByRole("button", { name: /account menu/i }));
  expect(screen.queryByRole("menuitem", { name: "Settings" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Log out" }));
  expect(logout).toHaveBeenCalled();
});

test("renders nothing when signed out", () => {
  const { container } = render(
    <AuthContext.Provider value={{ user: null, loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter><AppNav /></MemoryRouter>
    </AuthContext.Provider>
  );
  expect(container).toBeEmptyDOMElement();
});

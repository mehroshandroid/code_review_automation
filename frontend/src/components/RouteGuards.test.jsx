import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import { RequireAuth, RequirePermission, DashboardOrHome } from "./RouteGuards";
import { userWithRole } from "../testUtils/authUsers";

function renderAt(path, user, element) {
  return render(
    <AuthContext.Provider value={{ user, loading: false, login: jest.fn(), logout: jest.fn() }}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/my-reviews" element={<div>my reviews page</div>} />
          <Route path="/projects" element={<div>projects page</div>} />
          <Route path="/guarded" element={element} />
          <Route path="/" element={<RequireAuth><DashboardOrHome quarterly={<div>quarterly dashboard</div>}><div>dashboard</div></DashboardOrHome></RequireAuth>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

test("RequireAuth sends anonymous users to login", () => {
  renderAt("/", null);
  expect(screen.getByText("login page")).toBeInTheDocument();
});

test("RequirePermission renders children when allowed", () => {
  renderAt("/guarded", userWithRole("admin"), <RequirePermission anyOf={["users.manage"]}><div>secret</div></RequirePermission>);
  expect(screen.getByText("secret")).toBeInTheDocument();
});

test("RequirePermission redirects to the user's home when not allowed", () => {
  renderAt("/guarded", userWithRole("reviewer"), <RequirePermission anyOf={["users.manage"]}><div>secret</div></RequirePermission>);
  expect(screen.getByText("my reviews page")).toBeInTheDocument();
});

test.each([
  ["admin", "dashboard"],
  ["management", "dashboard"],
  ["project_manager", "dashboard"],
  ["reviewer", "my reviews page"],
  ["coordinator", "quarterly dashboard"],
])("%s lands on %s from /", (role, expected) => {
  renderAt("/", userWithRole(role));
  expect(screen.getByText(expected)).toBeInTheDocument();
});

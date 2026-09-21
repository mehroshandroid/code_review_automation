import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RequireAuth, RequireRole } from "./RouteGuards";
import { AuthContext } from "../context/AuthContext";

function renderWithAuth(value, path = "/protected") {
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route path="/" element={<div>Home page</div>} />
          <Route path="/protected" element={<RequireAuth><div>Secret content</div></RequireAuth>} />
          <Route
            path="/admin-only"
            element={<RequireRole roles={["admin"]}><div>Admin content</div></RequireRole>}
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

test("RequireAuth renders children when logged in", () => {
  renderWithAuth({ user: { id: "u1", role: "admin" }, loading: false });
  expect(screen.getByText("Secret content")).toBeInTheDocument();
});

test("RequireAuth redirects to /login when not logged in", () => {
  renderWithAuth({ user: null, loading: false });
  expect(screen.getByText("Login page")).toBeInTheDocument();
});

test("RequireAuth renders nothing while loading", () => {
  const { container } = renderWithAuth({ user: null, loading: true });
  expect(container).toBeEmptyDOMElement();
});

test("RequireRole renders children when the role matches", () => {
  renderWithAuth({ user: { id: "u1", role: "admin" }, loading: false }, "/admin-only");
  expect(screen.getByText("Admin content")).toBeInTheDocument();
});

test("RequireRole redirects to / when the role doesn't match", () => {
  renderWithAuth({ user: { id: "u1", role: "user" }, loading: false }, "/admin-only");
  expect(screen.getByText("Home page")).toBeInTheDocument();
});

test("RequireRole redirects to /login when not logged in", () => {
  renderWithAuth({ user: null, loading: false }, "/admin-only");
  expect(screen.getByText("Login page")).toBeInTheDocument();
});

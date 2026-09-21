import { render, screen, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";
import { getCurrentUser, login, logout } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getCurrentUser: jest.fn(),
  login: jest.fn(),
  logout: jest.fn(),
}));

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <div>Loading…</div>;
  return <div>{user ? `Logged in as ${user.email}` : "Not logged in"}</div>;
}

test("useAuth outside any provider returns a default admin user (keeps legacy tests working)", () => {
  render(<Probe />);
  expect(screen.getByText("Logged in as test-admin@example.com")).toBeInTheDocument();
});

test("AuthProvider starts loading, then resolves to the real user from getCurrentUser", async () => {
  getCurrentUser.mockResolvedValue({ id: "u1", email: "real@example.com", role: "reviewer" });
  render(<AuthProvider><Probe /></AuthProvider>);

  expect(screen.getByText("Loading…")).toBeInTheDocument();
  expect(await screen.findByText("Logged in as real@example.com")).toBeInTheDocument();
});

test("AuthProvider resolves to null (not logged in) when getCurrentUser rejects", async () => {
  getCurrentUser.mockRejectedValue({ response: { status: 401 } });
  render(<AuthProvider><Probe /></AuthProvider>);

  expect(await screen.findByText("Not logged in")).toBeInTheDocument();
});

test("login() updates the user in context", async () => {
  getCurrentUser.mockRejectedValue({ response: { status: 401 } });
  login.mockResolvedValue({ id: "u1", email: "new@example.com", role: "admin" });

  function LoginProbe() {
    const { user, login: doLogin } = useAuth();
    return (
      <div>
        <button onClick={() => doLogin("new@example.com", "pw")}>Log in</button>
        <div>{user ? user.email : "no user"}</div>
      </div>
    );
  }

  render(<AuthProvider><LoginProbe /></AuthProvider>);
  await screen.findByText("no user");

  screen.getByRole("button", { name: "Log in" }).click();

  expect(await screen.findByText("new@example.com")).toBeInTheDocument();
  expect(login).toHaveBeenCalledWith("new@example.com", "pw");
});

test("logout() clears the user from context", async () => {
  getCurrentUser.mockResolvedValue({ id: "u1", email: "real@example.com", role: "reviewer" });
  logout.mockResolvedValue();

  function LogoutProbe() {
    const { user, logout: doLogout } = useAuth();
    return (
      <div>
        <button onClick={doLogout}>Log out</button>
        <div>{user ? user.email : "no user"}</div>
      </div>
    );
  }

  render(<AuthProvider><LogoutProbe /></AuthProvider>);
  await screen.findByText("real@example.com");

  screen.getByRole("button", { name: "Log out" }).click();

  expect(await screen.findByText("no user")).toBeInTheDocument();
});

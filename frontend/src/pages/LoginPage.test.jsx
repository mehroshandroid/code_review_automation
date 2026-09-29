import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "./LoginPage";
import { AuthContext } from "../context/AuthContext";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

function renderWithAuth(loginImpl, initialEntries = ["/login"]) {
  const value = { user: null, loading: false, login: loginImpl, logout: jest.fn() };
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthContext.Provider value={value}>
        <LoginPage />
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockNavigate.mockClear();
});

test("submitting valid credentials logs in and navigates to /", async () => {
  const user = userEvent.setup();
  const loginImpl = jest.fn().mockResolvedValue({ id: "u1", email: "a@example.com", role: "admin" });
  renderWithAuth(loginImpl);

  await user.type(screen.getByLabelText(/email/i), "a@example.com");
  await user.type(screen.getByLabelText(/password/i), "correct horse");
  await user.click(screen.getByRole("button", { name: /log in/i }));

  await waitFor(() => expect(loginImpl).toHaveBeenCalledWith("a@example.com", "correct horse"));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/"));
});

test("shows the backend's error message on failed login and does not navigate", async () => {
  const user = userEvent.setup();
  const loginImpl = jest.fn().mockRejectedValue({ response: { data: { detail: "Incorrect email or password" } } });
  renderWithAuth(loginImpl);

  await user.type(screen.getByLabelText(/email/i), "a@example.com");
  await user.type(screen.getByLabelText(/password/i), "wrong");
  await user.click(screen.getByRole("button", { name: /log in/i }));

  expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test("shows a Sign in with Microsoft link pointing at the backend's Microsoft login route", async () => {
  renderWithAuth(jest.fn());

  const link = screen.getByRole("link", { name: /sign in with microsoft/i });
  expect(link).toHaveAttribute("href", expect.stringContaining("/auth/microsoft/login"));
});

test("shows an SSO failure message when the URL has error=sso_failed", async () => {
  renderWithAuth(jest.fn(), ["/login?error=sso_failed"]);

  expect(await screen.findByText(/microsoft sign-in failed/i)).toBeInTheDocument();
});

test("does not show an SSO failure message on a normal visit", async () => {
  renderWithAuth(jest.fn());

  expect(screen.queryByText(/microsoft sign-in failed/i)).not.toBeInTheDocument();
});

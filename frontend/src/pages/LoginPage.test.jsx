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

function renderWithAuth(loginImpl) {
  const value = { user: null, loading: false, login: loginImpl, logout: jest.fn() };
  return render(
    <MemoryRouter>
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

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmailSettingsSection from "./EmailSettingsSection";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getEmailStatus, getEmailOutbox, sendTestEmail, retryEmail } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getEmailStatus: jest.fn(), getEmailOutbox: jest.fn(), sendTestEmail: jest.fn(), retryEmail: jest.fn(),
}));

const status = { mode: "log", from_address: null, from_name: "CodeAssure", base_url: "http://localhost:3000", configured: true, problems: [] };
const email = (extra) => ({ id: "e1", event: "review_ready", recipient_email: "rae@example.com", recipient_name: "Rae",
  subject: "Ready for your review: Moove · iOS (Q4 2026)", status: "logged", attempts: 1, last_error: null,
  created_at: "2026-10-08T10:00:00Z", sent_at: "2026-10-08T10:00:05Z", ...extra });

beforeEach(() => {
  jest.resetAllMocks();
  getEmailStatus.mockResolvedValue(status);
  getEmailOutbox.mockResolvedValue([email(), email({ id: "e2", status: "failed", last_error: "SMTP send failed: SMTPAuthenticationError", attempts: 5 })]);
});

function renderAs(role) {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <EmailSettingsSection />
    </AuthContext.Provider>
  );
}

test("shows the delivery status and recent emails", async () => {
  renderAs("admin");
  expect(await screen.findByText(/Log only/)).toBeInTheDocument();
  const table = screen.getByRole("table");
  expect(within(table).getAllByText("Ready for your review: Moove · iOS (Q4 2026)", { selector: "td" })).toHaveLength(2);
  expect(within(table).getByText("SMTP send failed: SMTPAuthenticationError")).toBeInTheDocument();
});

test("lists configuration problems", async () => {
  getEmailStatus.mockResolvedValue({ ...status, mode: "smtp", configured: false, problems: ["SMTP_HOST is not set."] });
  renderAs("admin");
  expect(await screen.findByText("SMTP_HOST is not set.")).toBeInTheDocument();
});

test("send test email and retry a failed one", async () => {
  const user = userEvent.setup();
  sendTestEmail.mockResolvedValue(email({ id: "e3", event: "test_email", status: "pending" }));
  retryEmail.mockResolvedValue(email({ id: "e2", status: "pending" }));
  renderAs("admin");
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "Send test email" }));
  await waitFor(() => expect(sendTestEmail).toHaveBeenCalled());
  expect(await screen.findByText(/Test email queued/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(retryEmail).toHaveBeenCalledWith("e2"));
});

test("hidden for non-admins", () => {
  const { container } = renderAs("management");
  expect(container).toBeEmptyDOMElement();
  expect(getEmailStatus).not.toHaveBeenCalled();
});

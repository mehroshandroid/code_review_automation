import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AutomationSettingsSection from "./AutomationSettingsSection";
import { AuthContext } from "../context/AuthContext";
import { userWithRole } from "../testUtils/authUsers";
import { getAutomationSettings, saveDevopsPat, saveAutoCompileModes } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getAutomationSettings: jest.fn(), saveDevopsPat: jest.fn(), saveAutoCompileModes: jest.fn(),
}));

const settings = {
  pat: { configured: true, last4: "1234", updated_at: "2026-10-01T00:00:00Z", updated_by_name: "Ada" },
  compile_modes: { Android: "compiler", ".NET": "compiler", iOS: "static" },
};

beforeEach(() => {
  jest.resetAllMocks();
  getAutomationSettings.mockResolvedValue(settings);
});

function renderAs(role) {
  return render(
    <AuthContext.Provider value={{ user: userWithRole(role), loading: false, login: jest.fn(), logout: jest.fn() }}>
      <AutomationSettingsSection />
    </AuthContext.Provider>
  );
}

test("shows the PAT summary without the secret", async () => {
  renderAs("admin");
  expect(await screen.findByText(/Configured · ••••1234/)).toBeInTheDocument();
  expect(screen.getByText(/by Ada/)).toBeInTheDocument();
});

test("admin can save a new PAT", async () => {
  const user = userEvent.setup();
  saveDevopsPat.mockResolvedValue({ ...settings.pat, last4: "9999" });
  renderAs("admin");
  await screen.findByText(/••••1234/);
  await user.type(screen.getByLabelText("New Azure DevOps PAT"), "newpat9999");
  await user.click(screen.getByRole("button", { name: "Save PAT" }));
  await waitFor(() => expect(saveDevopsPat).toHaveBeenCalledWith("newpat9999"));
  expect(await screen.findByText(/••••9999/)).toBeInTheDocument();
  expect(screen.getByLabelText("New Azure DevOps PAT")).toHaveValue("");
});

test("management cannot edit the PAT but can save compile checks", async () => {
  const user = userEvent.setup();
  saveAutoCompileModes.mockResolvedValue({ Android: "compiler", ".NET": "compiler", iOS: "compiler" });
  renderAs("management");
  await screen.findByText(/••••1234/);
  expect(screen.queryByLabelText("New Azure DevOps PAT")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Compile check for iOS"), "compiler");
  await user.click(screen.getByRole("button", { name: "Save compile checks" }));
  await waitFor(() => expect(saveAutoCompileModes).toHaveBeenCalledWith({ Android: "compiler", ".NET": "compiler", iOS: "compiler" }));
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
});

test("not configured state", async () => {
  getAutomationSettings.mockResolvedValue({ ...settings, pat: { configured: false, last4: null, updated_at: null, updated_by_name: null } });
  renderAs("admin");
  expect(await screen.findByText(/Not configured/)).toBeInTheDocument();
});

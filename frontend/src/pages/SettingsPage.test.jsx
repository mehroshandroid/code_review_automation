import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SettingsPage from "./SettingsPage";
import {
  getLlmProviderSettings, updateLlmProviderSettings, getOllamaModels,
  getClauseChecklists, upsertClauseChecklist, deleteClauseChecklist,
  getSampleTemplates, uploadSampleTemplate, deleteSampleTemplate, previewSampleTemplate,
} from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getLlmProviderSettings: jest.fn(),
  updateLlmProviderSettings: jest.fn(),
  getOllamaModels: jest.fn(),
  getClauseChecklists: jest.fn(),
  upsertClauseChecklist: jest.fn(),
  deleteClauseChecklist: jest.fn(),
  getSampleTemplates: jest.fn(),
  uploadSampleTemplate: jest.fn(),
  deleteSampleTemplate: jest.fn(),
  previewSampleTemplate: jest.fn(),
}));

const previewCategories = [
  {
    id: "2",
    name: "Reliability, Security & Observability",
    sub_criteria: [
      { id: "2.3", description: "No hardcoded secrets" },
      { id: "2.4", description: "Proper authentication handling" },
    ],
  },
];

beforeEach(() => {
  jest.resetAllMocks();
  getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: null });
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b", "mistral:latest"]);
  getClauseChecklists.mockResolvedValue([]);
  getSampleTemplates.mockResolvedValue([]);
  previewSampleTemplate.mockResolvedValue(previewCategories);
});

function renderSettings() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>
  );
}

describe("LLM provider section", () => {
  test("shows the currently configured default highlighted", async () => {
    getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "azure", default_ollama_model: null });
    renderSettings();

    await waitFor(() => expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary"));
  });

  test("shows the Ollama model field only when Ollama is selected", async () => {
    const user = userEvent.setup();
    getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "azure", default_ollama_model: null });
    renderSettings();

    await waitFor(() => expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary"));
    expect(screen.queryByLabelText(/default ollama model/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ollama (local)" }));
    expect(await screen.findByLabelText(/default ollama model/i)).toBeInTheDocument();
  });

  test("saves the selected provider and model", async () => {
    const user = userEvent.setup();
    getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: "" });
    updateLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: "qwen2.5-coder:7b" });
    renderSettings();

    await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));
    await screen.findByLabelText(/default ollama model/i);
    await user.selectOptions(screen.getByLabelText(/default ollama model/i), "qwen2.5-coder:7b");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateLlmProviderSettings).toHaveBeenCalledWith("ollama", "qwen2.5-coder:7b"));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  test("shows a dropdown of installed Ollama models to choose from", async () => {
    getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: "mistral:latest" });
    renderSettings();

    const select = await screen.findByLabelText(/default ollama model/i);
    expect(select.tagName).toBe("SELECT");
    expect(select).toHaveValue("mistral:latest");
    expect(screen.getByRole("option", { name: "qwen2.5-coder:7b" })).toBeInTheDocument();
  });

  test("falls back to a free-text model field when Ollama has no installed models", async () => {
    getLlmProviderSettings.mockResolvedValue({ default_llm_provider: "ollama", default_ollama_model: "" });
    getOllamaModels.mockResolvedValue([]);
    renderSettings();

    const input = await screen.findByLabelText(/default ollama model/i);
    expect(input.tagName).toBe("INPUT");
    expect(screen.getByText(/couldn't reach ollama/i)).toBeInTheDocument();
  });
});

describe("Clause checklist section", () => {
  test("lists existing checklists", async () => {
    getClauseChecklists.mockResolvedValue([
      { platform: ".NET", sub_id: "2.4", checklist_text: "Check JWT config" },
    ]);
    renderSettings();

    expect(await screen.findByText("Check JWT config")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: ".NET" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2.4" })).toBeInTheDocument();
  });

  test("adding a new checklist calls upsert and refreshes the list", async () => {
    const user = userEvent.setup();
    getClauseChecklists.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { platform: "Android", sub_id: "2.3", checklist_text: "Check for hardcoded secrets" },
    ]);
    upsertClauseChecklist.mockResolvedValue({ platform: "Android", sub_id: "2.3", checklist_text: "Check for hardcoded secrets" });
    renderSettings();

    await waitFor(() => expect(getClauseChecklists).toHaveBeenCalledTimes(1));

    await user.selectOptions(screen.getByLabelText(/platform/i), "Android");
    await user.type(screen.getByLabelText(/sub-clause id/i), "2.3");
    await user.type(screen.getByLabelText(/checklist text/i), "Check for hardcoded secrets");
    await user.click(screen.getByRole("button", { name: /save checklist/i }));

    await waitFor(() => expect(upsertClauseChecklist).toHaveBeenCalledWith("Android", "2.3", "Check for hardcoded secrets"));
    expect(await screen.findByText("Check for hardcoded secrets")).toBeInTheDocument();
  });

  test("editing an existing checklist populates the form", async () => {
    const user = userEvent.setup();
    getClauseChecklists.mockResolvedValue([
      { platform: ".NET", sub_id: "2.4", checklist_text: "Check JWT config" },
    ]);
    renderSettings();

    await screen.findByText("Check JWT config");
    await user.click(screen.getByRole("button", { name: /edit/i }));

    expect(screen.getByLabelText(/sub-clause id/i)).toHaveValue("2.4");
    expect(screen.getByLabelText(/checklist text/i)).toHaveValue("Check JWT config");
  });

  test("deleting a checklist calls the delete endpoint and refreshes the list", async () => {
    const user = userEvent.setup();
    getClauseChecklists.mockResolvedValueOnce([
      { platform: ".NET", sub_id: "2.4", checklist_text: "Check JWT config" },
    ]).mockResolvedValueOnce([]);
    deleteClauseChecklist.mockResolvedValue(undefined);
    renderSettings();

    await screen.findByText("Check JWT config");
    await user.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteClauseChecklist).toHaveBeenCalledWith(".NET", "2.4"));
    await waitFor(() => expect(screen.queryByText("Check JWT config")).not.toBeInTheDocument());
  });

  test("clicking Preview clauses opens a dialog showing the selected platform's clause structure", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: /preview clauses/i }));

    expect(await screen.findByText(/no hardcoded secrets/i)).toBeInTheDocument();
    expect(screen.getByText(/proper authentication handling/i)).toBeInTheDocument();
    expect(previewSampleTemplate).toHaveBeenCalledWith("Android");
  });

  test("clicking Use on a clause fills the Sub-clause ID field and closes the dialog", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: /preview clauses/i }));
    await screen.findByText(/no hardcoded secrets/i);
    const useButtons = screen.getAllByRole("button", { name: "Use" });
    await user.click(useButtons[1]);

    expect(screen.getByLabelText(/sub-clause id/i)).toHaveValue("2.4");
    expect(screen.queryByText(/no hardcoded secrets/i)).not.toBeInTheDocument();
  });

  test("shows a helpful message in the preview dialog when no sample sheet is configured for the platform", async () => {
    const user = userEvent.setup();
    previewSampleTemplate.mockRejectedValue({ response: { status: 404 } });
    renderSettings();

    await user.click(screen.getByRole("button", { name: /preview clauses/i }));

    expect(await screen.findByText(/no sample sheet uploaded for android/i)).toBeInTheDocument();
  });
});

describe("Sample template section", () => {
  test("shows 'No default configured' for platforms without a stored template", async () => {
    renderSettings();

    const androidRow = (await screen.findByText("Android", { selector: ".card-title" })).closest(".card");
    expect(within(androidRow).getByText(/no default configured/i)).toBeInTheDocument();
    expect(within(androidRow).getByText(/upload/i)).toBeInTheDocument();
  });

  test("shows the current filename and a Replace control for platforms with a stored template", async () => {
    getSampleTemplates.mockResolvedValue([
      { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
    ]);
    renderSettings();

    const androidRow = (await screen.findByText("Android", { selector: ".card-title" })).closest(".card");
    expect(within(androidRow).getByText(/current default: android-default\.xlsx/i)).toBeInTheDocument();
    expect(within(androidRow).getByText(/replace/i)).toBeInTheDocument();
    expect(within(androidRow).getByRole("button", { name: /remove/i })).toBeInTheDocument();
  });

  test("uploading a file for a platform calls uploadSampleTemplate and refreshes the list", async () => {
    const user = userEvent.setup();
    getSampleTemplates.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
    ]);
    uploadSampleTemplate.mockResolvedValue({ platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" });
    renderSettings();

    await waitFor(() => expect(getSampleTemplates).toHaveBeenCalledTimes(1));
    const file = new File(["xlsx content"], "android-default.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const input = screen.getByLabelText(/upload sample template for android/i);
    await user.upload(input, file);

    await waitFor(() => expect(uploadSampleTemplate).toHaveBeenCalledWith("Android", file));
    expect(await screen.findByText(/current default: android-default\.xlsx/i)).toBeInTheDocument();
  });

  test("removing a configured template calls deleteSampleTemplate and refreshes the list", async () => {
    const user = userEvent.setup();
    getSampleTemplates.mockResolvedValueOnce([
      { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
    ]).mockResolvedValueOnce([]);
    deleteSampleTemplate.mockResolvedValue(undefined);
    renderSettings();

    const androidRow = (await screen.findByText(/current default: android-default\.xlsx/i)).closest(".card");
    await user.click(within(androidRow).getByRole("button", { name: /remove/i }));

    await waitFor(() => expect(deleteSampleTemplate).toHaveBeenCalledWith("Android"));
    await waitFor(() => expect(within(androidRow).getByText(/no default configured/i)).toBeInTheDocument());
  });

  test("does not show a Preview button for platforms without a stored template", async () => {
    renderSettings();

    const androidRow = (await screen.findByText("Android", { selector: ".card-title" })).closest(".card");
    expect(within(androidRow).queryByRole("button", { name: /preview/i })).not.toBeInTheDocument();
  });

  test("clicking Preview for a configured platform opens a read-only clause dialog with no Use buttons", async () => {
    const user = userEvent.setup();
    getSampleTemplates.mockResolvedValue([
      { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" },
    ]);
    renderSettings();

    const androidRow = (await screen.findByText("Android", { selector: ".card-title" })).closest(".card");
    await user.click(within(androidRow).getByRole("button", { name: /preview/i }));

    expect(await screen.findByText(/no hardcoded secrets/i)).toBeInTheDocument();
    expect(previewSampleTemplate).toHaveBeenCalledWith("Android");
    expect(screen.queryByRole("button", { name: "Use" })).not.toBeInTheDocument();
  });
});

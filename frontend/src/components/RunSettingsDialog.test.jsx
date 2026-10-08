import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RunSettingsDialog from "./RunSettingsDialog";
import { getOllamaModels, saveQueueItemSettings } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getOllamaModels: jest.fn(), saveQueueItemSettings: jest.fn() }));

const defaults = { llm_provider: "azure", llm_model: null, compile_modes: { Android: "compiler", ".NET": "compiler", iOS: "static" } };
const item = { cycle_id: "c1", platform: "Android", project_name: "Alpha", quarter: 4, year: 2026,
  override_llm_provider: null, override_llm_model: null, override_compile_mode: null };

beforeEach(() => {
  jest.resetAllMocks();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b", "llama3"]);
});

test("labels the org defaults", () => {
  render(<RunSettingsDialog item={item} defaults={defaults} onSaved={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByRole("option", { name: "Org default (Azure OpenAI)" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Org default (Docker lint)" })).toBeInTheDocument();
});

test("choosing Ollama shows installed models and saves overrides", async () => {
  const user = userEvent.setup();
  const onSaved = jest.fn();
  saveQueueItemSettings.mockResolvedValue({});
  render(<RunSettingsDialog item={item} defaults={defaults} onSaved={onSaved} onClose={jest.fn()} />);
  await user.selectOptions(screen.getByLabelText("LLM provider"), "ollama");
  await user.selectOptions(await screen.findByLabelText("Ollama model"), "llama3");
  await user.selectOptions(screen.getByLabelText("Compile check"), "static");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(saveQueueItemSettings).toHaveBeenCalledWith("c1", "Android", { llmProvider: "ollama", llmModel: "llama3", compileMode: "static" }));
  expect(onSaved).toHaveBeenCalled();
});

test("clear overrides sends nulls", async () => {
  const user = userEvent.setup();
  saveQueueItemSettings.mockResolvedValue({});
  render(<RunSettingsDialog item={{ ...item, override_llm_provider: "claude", override_compile_mode: "static" }} defaults={defaults} onSaved={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByLabelText("LLM provider")).toHaveValue("claude");
  await user.click(screen.getByRole("button", { name: "Clear overrides" }));
  await waitFor(() => expect(saveQueueItemSettings).toHaveBeenCalledWith("c1", "Android", { llmProvider: null, llmModel: null, compileMode: null }));
});

test("shows API errors", async () => {
  const user = userEvent.setup();
  saveQueueItemSettings.mockRejectedValue({ response: { data: { detail: "A running or completed review's settings can't change." } } });
  render(<RunSettingsDialog item={item} defaults={defaults} onSaved={jest.fn()} onClose={jest.fn()} />);
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("A running or completed review's settings can't change.")).toBeInTheDocument();
});

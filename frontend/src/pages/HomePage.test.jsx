import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import HomePage from "./HomePage";
import { getLlmProvider, getOllamaModel } from "../services/llmProviderStorage";
import { getOllamaModels } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getOllamaModels: jest.fn(),
}));

beforeEach(() => {
  localStorage.clear();
  jest.resetAllMocks();
});

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

test("renders a link for each platform pointing at /review/<id>", async () => {
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  renderHome();
  expect(screen.getByRole("link", { name: /android/i })).toHaveAttribute("href", "/review/android");
  expect(screen.getByRole("link", { name: /ios/i })).toHaveAttribute("href", "/review/ios");
  expect(screen.getByRole("link", { name: /\.net/i })).toHaveAttribute("href", "/review/dotnet");
  expect(screen.getByRole("link", { name: /web \(react\)/i })).toHaveAttribute("href", "/review/web");
});

test("defaults to Ollama highlighted when models are available", async () => {
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  renderHome();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).not.toHaveClass("btn-primary");
});

test("clicking Azure OpenAI persists the choice and updates the highlighted button", async () => {
  const user = userEvent.setup();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  renderHome();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));

  await user.click(screen.getByRole("button", { name: "Azure OpenAI" }));

  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary");
  expect(getLlmProvider()).toBe("azure");
});

test("shows a model dropdown populated from installed models, defaulting to the first one", async () => {
  getOllamaModels.mockResolvedValue(["mistral:latest", "qwen2.5-coder:7b"]);
  renderHome();

  const select = await screen.findByLabelText("Ollama model");
  expect(select.value).toBe("mistral:latest");
  expect(screen.getByRole("option", { name: "qwen2.5-coder:7b" })).toBeInTheDocument();
});

test("selecting a model persists it to localStorage", async () => {
  const user = userEvent.setup();
  getOllamaModels.mockResolvedValue(["mistral:latest", "qwen2.5-coder:7b"]);
  renderHome();

  const select = await screen.findByLabelText("Ollama model");
  await user.selectOptions(select, "qwen2.5-coder:7b");

  expect(getOllamaModel()).toBe("qwen2.5-coder:7b");
});

test("disables Ollama and forces Azure when no local models are installed", async () => {
  getOllamaModels.mockResolvedValue([]);
  renderHome();

  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toBeDisabled());
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary");
  expect(screen.queryByLabelText("Ollama model")).not.toBeInTheDocument();
  // Forcing the effective provider does not overwrite the stored preference.
  expect(getLlmProvider()).toBe("ollama");
});

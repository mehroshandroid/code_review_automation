import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import HomePage from "./HomePage";
import { getLlmProvider } from "../services/llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

test("renders a link for each platform pointing at /review/<id>", () => {
  renderHome();
  expect(screen.getByRole("link", { name: /android/i })).toHaveAttribute("href", "/review/android");
  expect(screen.getByRole("link", { name: /ios/i })).toHaveAttribute("href", "/review/ios");
  expect(screen.getByRole("link", { name: /\.net/i })).toHaveAttribute("href", "/review/dotnet");
  expect(screen.getByRole("link", { name: /web \(react\)/i })).toHaveAttribute("href", "/review/web");
});

test("defaults the LLM toggle to Azure OpenAI highlighted", () => {
  renderHome();
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Ollama (local)" })).not.toHaveClass("btn-primary");
});

test("clicking Ollama persists the choice to localStorage and updates the highlighted button", async () => {
  const user = userEvent.setup();
  renderHome();

  await user.click(screen.getByRole("button", { name: "Ollama (local)" }));

  expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).not.toHaveClass("btn-primary");
  expect(getLlmProvider()).toBe("ollama");
});

import { getLlmProvider, setLlmProvider } from "./llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

test("defaults to azure when nothing is stored", () => {
  expect(getLlmProvider()).toBe("azure");
});

test("returns a previously-stored value", () => {
  localStorage.setItem("llmProvider", "ollama");
  expect(getLlmProvider()).toBe("ollama");
});

test("setLlmProvider writes to localStorage under the expected key", () => {
  setLlmProvider("ollama");
  expect(localStorage.getItem("llmProvider")).toBe("ollama");
  expect(getLlmProvider()).toBe("ollama");
});

import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel, initializeLlmProviderDefault } from "./llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

test("returns null when nothing is stored", () => {
  expect(getLlmProvider()).toBeNull();
});

test("returns a previously-stored value", () => {
  localStorage.setItem("llmProvider", "azure");
  expect(getLlmProvider()).toBe("azure");
});

test("setLlmProvider writes to localStorage under the expected key", () => {
  setLlmProvider("azure");
  expect(localStorage.getItem("llmProvider")).toBe("azure");
  expect(getLlmProvider()).toBe("azure");
});

test("getOllamaModel returns null when nothing is stored", () => {
  expect(getOllamaModel()).toBeNull();
});

test("setOllamaModel writes to localStorage under the expected key", () => {
  setOllamaModel("qwen2.5-coder:7b");
  expect(localStorage.getItem("ollamaModel")).toBe("qwen2.5-coder:7b");
  expect(getOllamaModel()).toBe("qwen2.5-coder:7b");
});

test("initializeLlmProviderDefault seeds localStorage when nothing is stored", () => {
  initializeLlmProviderDefault("azure");
  expect(getLlmProvider()).toBe("azure");
});

test("initializeLlmProviderDefault does not override an explicitly-chosen provider", () => {
  setLlmProvider("azure");
  initializeLlmProviderDefault("ollama");
  expect(getLlmProvider()).toBe("azure");
});

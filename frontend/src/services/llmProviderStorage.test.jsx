import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel } from "./llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

test("defaults to ollama when nothing is stored", () => {
  expect(getLlmProvider()).toBe("ollama");
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

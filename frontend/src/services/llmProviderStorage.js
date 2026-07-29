const STORAGE_KEY = "llmProvider";
const DEFAULT_PROVIDER = "ollama";
const MODEL_STORAGE_KEY = "ollamaModel";

export function getLlmProvider() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_PROVIDER;
}

export function setLlmProvider(provider) {
  localStorage.setItem(STORAGE_KEY, provider);
}

export function getOllamaModel() {
  return localStorage.getItem(MODEL_STORAGE_KEY) || null;
}

export function setOllamaModel(model) {
  localStorage.setItem(MODEL_STORAGE_KEY, model);
}

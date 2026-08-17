const STORAGE_KEY = "llmProvider";
const MODEL_STORAGE_KEY = "ollamaModel";

export function getLlmProvider() {
  return localStorage.getItem(STORAGE_KEY);
}

export function setLlmProvider(provider) {
  localStorage.setItem(STORAGE_KEY, provider);
}

export function initializeLlmProviderDefault(orgDefault) {
  if (localStorage.getItem(STORAGE_KEY) === null) {
    localStorage.setItem(STORAGE_KEY, orgDefault);
  }
}

export function getOllamaModel() {
  return localStorage.getItem(MODEL_STORAGE_KEY) || null;
}

export function setOllamaModel(model) {
  localStorage.setItem(MODEL_STORAGE_KEY, model);
}

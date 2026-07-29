const STORAGE_KEY = "llmProvider";
const DEFAULT_PROVIDER = "azure";

export function getLlmProvider() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_PROVIDER;
}

export function setLlmProvider(provider) {
  localStorage.setItem(STORAGE_KEY, provider);
}

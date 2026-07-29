const STORAGE_KEY = "compileCheckMode";
const DEFAULT_MODE = "compiler";

export function getCompileCheckMode() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_MODE;
}

export function setCompileCheckMode(mode) {
  localStorage.setItem(STORAGE_KEY, mode);
}

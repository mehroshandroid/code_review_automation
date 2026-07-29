import { getCompileCheckMode, setCompileCheckMode } from "./compileCheckModeStorage";

beforeEach(() => {
  localStorage.clear();
});

test("defaults to compiler when nothing is stored", () => {
  expect(getCompileCheckMode()).toBe("compiler");
});

test("returns a previously-stored value", () => {
  localStorage.setItem("compileCheckMode", "static");
  expect(getCompileCheckMode()).toBe("static");
});

test("setCompileCheckMode writes to localStorage under the expected key", () => {
  setCompileCheckMode("static");
  expect(localStorage.getItem("compileCheckMode")).toBe("static");
  expect(getCompileCheckMode()).toBe("static");
});

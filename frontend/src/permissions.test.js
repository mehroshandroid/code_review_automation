import { hasPermission, hasAny, initialsFor, ROLES, ROLE_LABELS } from "./permissions";

test("hasPermission reads the user's permission list", () => {
  expect(hasPermission({ permissions: ["chat.use"] }, "chat.use")).toBe(true);
  expect(hasPermission({ permissions: [] }, "chat.use")).toBe(false);
  expect(hasPermission(null, "chat.use")).toBe(false);
});

test("hasAny", () => {
  expect(hasAny({ permissions: ["a"] }, ["b", "a"])).toBe(true);
  expect(hasAny({ permissions: ["a"] }, ["b"])).toBe(false);
});

test("initials from name, else from email", () => {
  expect(initialsFor({ name: "Mehrosh Mehboob", email: "x@y.com" })).toBe("MM");
  expect(initialsFor({ name: "Cher", email: "x@y.com" })).toBe("C");
  expect(initialsFor({ name: null, email: "jane.doe@example.com" })).toBe("JD");
  expect(initialsFor({ email: "admin@example.com" })).toBe("A");
});

test("five roles with labels", () => {
  expect(ROLES).toEqual(["admin", "management", "coordinator", "reviewer", "project_manager"]);
  expect(ROLE_LABELS.project_manager).toBe("Project Manager");
});

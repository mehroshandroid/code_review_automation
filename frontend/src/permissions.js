export const ROLES = ["admin", "management", "coordinator", "reviewer", "project_manager"];

export const ROLE_LABELS = {
  admin: "Admin",
  management: "Management",
  coordinator: "Coordinator",
  reviewer: "Reviewer",
  project_manager: "Project Manager",
};

export function hasPermission(user, permission) {
  return !!user?.permissions?.includes(permission);
}

export function hasAny(user, permissions) {
  return permissions.some((permission) => hasPermission(user, permission));
}

export function initialsFor(user) {
  const source = user?.name?.trim()
    ? user.name.trim().split(/\s+/)
    : (user?.email || "").split("@")[0].split(/[._-]+/);
  return source.filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}

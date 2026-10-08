// Test-only mirror of backend/app/auth/permissions.py PERMISSIONS/HOME_PATHS,
// so component tests can build realistic users. Production code reads
// permissions from GET /api/auth/me instead.
const ROLE_PERMISSIONS = {
  admin: [
    "chat.use", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
    "projects.delete", "projects.rename", "projects.view", "reviews.assign_reviewer", "reviews.create",
    "reviews.delete", "reviews.edit", "reviews.finalize_own", "settings.manage", "users.manage",
  ],
  management: [
    "chat.use", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
    "projects.delete", "projects.rename", "projects.view", "reviews.assign_reviewer", "reviews.create",
    "reviews.edit", "reviews.finalize_own", "settings.manage",
  ],
  coordinator: ["projects.assign_pm", "projects.create", "projects.rename", "projects.view", "reviews.assign_reviewer"],
  reviewer: ["my_reviews.view", "reviews.finalize_own"],
  project_manager: ["chat.use", "dashboard.view_assigned"],
};

const HOME_PATHS = { admin: "/", management: "/", project_manager: "/", reviewer: "/my-reviews", coordinator: "/projects" };

export function userWithRole(role, overrides = {}) {
  return {
    id: `${role}-id`, email: `${role}@example.com`, name: null, role,
    permissions: ROLE_PERMISSIONS[role], home_path: HOME_PATHS[role], ...overrides,
  };
}

export const ADMIN_PERMISSIONS = ROLE_PERMISSIONS.admin;

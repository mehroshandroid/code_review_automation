// Test-only mirror of backend/app/auth/permissions.py PERMISSIONS/HOME_PATHS,
// so component tests can build realistic users. Production code reads
// permissions from GET /api/auth/me instead.
const ROLE_PERMISSIONS = {
  admin: [
    "chat.use", "cycles.initiate", "cycles.submit_urls", "cycles.view", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
    "projects.delete", "projects.edit", "projects.view", "reviews.assign_reviewer", "reviews.create",
    "reviews.delete", "reviews.edit", "queue.manage", "reviews.finalize_own", "settings.devops_pat", "settings.manage", "users.manage",
  ],
  management: [
    "chat.use", "cycles.initiate", "cycles.submit_urls", "cycles.view", "dashboard.view_all", "my_reviews.view", "projects.assign_pm", "projects.create",
    "projects.delete", "projects.edit", "projects.view", "reviews.assign_reviewer", "reviews.create",
    "reviews.edit", "reviews.finalize_own", "settings.manage",
  ],
  coordinator: ["cycles.initiate", "cycles.submit_urls", "cycles.view", "projects.assign_pm", "projects.create", "projects.edit", "projects.view", "reviews.assign_reviewer"],
  reviewer: ["my_reviews.view", "reviews.finalize_own"],
  project_manager: ["chat.use", "cycles.submit_urls", "dashboard.view_assigned"],
};

const HOME_PATHS = { admin: "/", management: "/", project_manager: "/", reviewer: "/my-reviews", coordinator: "/" };

export function userWithRole(role, overrides = {}) {
  return {
    id: `${role}-id`, email: `${role}@example.com`, name: null, role,
    permissions: ROLE_PERMISSIONS[role], home_path: HOME_PATHS[role], ...overrides,
  };
}

export const ADMIN_PERMISSIONS = ROLE_PERMISSIONS.admin;

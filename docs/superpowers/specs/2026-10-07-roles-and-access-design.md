# Roles & Access (Part 1 of the Quarterly Review Workflow) — Design Spec

**Date:** 2026-10-07
**Status:** Approved in brainstorming, awaiting written-spec review
**Branch base:** `claude-cli-provider`

## Context

After the POC demo, CodeAssure moves to real, organization-wide use. The intended end state is a quarterly review process. A Coordinator initiates each quarter's review for a project and assigns a reviewer per platform. The Project Manager supplies an Azure DevOps repo URL for each platform. The AI review then runs on its own, the reviewer finalizes it, and the PM receives the final result by email.

That work is split into three sub-projects, each with its own spec, plan and implementation:

1. **Roles & access** (this spec): new roles, project-scoped visibility for PMs, the reviewer's own page, and a shared professional navbar.
2. **Quarterly cycles** (later spec): the cycle and assignment data model, the Coordinator's initiation screen and stage tracker, PM URL entry, autonomous execution with an org-wide PAT, and review progress saved in the database.
3. **Notifications** (later spec): an email service (Microsoft Graph preferred, SMTP fallback), the four workflow emails, and reminders.

This spec covers **Part 1 only**. Part 1 must be useful on its own: it ships the new roles and scoping with no dependency on Parts 2 or 3.

## Goals

- Five roles with clearly defined capabilities, enforced in one place on the backend.
- Project Managers see the existing dashboard, limited to the projects an admin assigned them.
- Reviewers get a "My reviews" page and can finalize only the reviews assigned to them. They lose the org-wide dashboard.
- One shared navbar that shows links for the user's role and looks professional.

## Non-goals (Part 1)

- Quarterly cycles, per-project platform lists, the org-wide DevOps PAT, autonomous reviews (Part 2).
- Any email or notification (Part 3).
- A redesign of the whole app. Only the navbar is fully restyled, plus alignment fixes on the screens this spec already touches.

## Roles

| Role | Description |
|---|---|
| `admin` | Everything, including user management and deleting reviews |
| `management` | The old `reviewer` privileges: full dashboard, run reviews, edit scores, Settings |
| `coordinator` | Will run quarterly cycles in Part 2. In Part 1, a placeholder home page only |
| `reviewer` | Finalizes reviews assigned to them. No dashboard and no Settings |
| `project_manager` | Read-only dashboard limited to assigned projects, plus a chatbot limited the same way |

The old `user` role is **retired**. Existing `user` accounts are migrated to `project_manager` with no projects assigned, so they see nothing until an admin assigns projects.

**Rollout note:** existing `reviewer` accounts keep the `reviewer` role but **lose the org-wide dashboard and Settings**. Before deploying, an admin should move anyone who still needs the full dashboard to `management`.

## Capability matrix

| Capability key | admin | management | coordinator | reviewer | project_manager |
|---|---|---|---|---|---|
| `dashboard.view_all` | ✓ | ✓ | | | |
| `dashboard.view_assigned` | | | | | ✓ |
| `reviews.create` (run and upload ad-hoc reviews, clause overrides and preview) | ✓ | ✓ | | | |
| `reviews.edit` (scores, status, any review) | ✓ | ✓ | | | |
| `reviews.assign_reviewer` | ✓ | ✓ | | | |
| `reviews.finalize_own` (edit scores and status of reviews where `reviewer_id` is you) | ✓ | ✓ | | ✓ | |
| `reviews.delete` | ✓ | | | | |
| `my_reviews.view` | ✓ | ✓ | | ✓ | |
| `settings.manage` | ✓ | ✓ | | | |
| `users.manage` (including PM project assignment) | ✓ | | | | |
| `projects.rename` | ✓ | | | | |
| `chat.use` (limited to the user's visible projects) | ✓ | ✓ | | | ✓ |

**Home page by role:** admin and management go to `/` (Dashboard), project_manager to `/` (scoped Dashboard), reviewer to `/my-reviews`, and coordinator to `/cycles`.

Creating projects (`POST /api/projects`) keeps its current behaviour under `reviews.create`, because projects are created from the Start Review and Upload dialogs.

## Data model changes (one Alembic migration)

- `users.role` allowed values: `admin`, `management`, `coordinator`, `reviewer`, `project_manager`. This is a plain string column, validated in the API through `ALLOWED_ROLES`.
- New nullable column `users.name` (`String`). It is filled from the Microsoft SSO profile (`name` claim) when an account is first provisioned or linked, and an admin can edit it. It is used for avatar initials and display, and later for email salutations.
- New table `project_managers`:
  - `user_id` → `users.id`, `ON DELETE CASCADE`
  - `project_id` → `projects.id`, `ON DELETE CASCADE`
  - Primary key `(user_id, project_id)`
- Data migration: `UPDATE users SET role='project_manager' WHERE role='user'`.
- Downgrade: turn `project_manager` back into `user`, turn `management` and `coordinator` back into `reviewer`, then drop the table and the column.

## Backend design

### `app/auth/permissions.py` (new)

- `PERMISSIONS: dict[str, frozenset[str]]`: maps each capability to its roles, exactly as in the matrix above. This is the single source of truth.
- `HOME_PATHS: dict[str, str]`: maps each role to its home path.
- `can(user, capability) -> bool`.
- `require_permission(capability)`: a FastAPI dependency that returns 403 when the user's role lacks the capability. Every existing `require_roles(...)` call is replaced with it, and `require_roles` is then removed.
- `async visible_project_ids(session, user) -> set[str] | None`:
  - `None` means all projects (`dashboard.view_all`).
  - For `dashboard.view_assigned`, it returns the user's rows in `project_managers`.
  - Otherwise it returns the empty set, so even direct API calls from coordinators and reviewers return no dashboard data.

### Data layer (`app/db/crud.py`)

- `list_projects`, `list_reviews`, `list_review_years` and `list_reviews_for_project` accept `project_ids: set[str] | None = None`.
  - `None` means no filter.
  - An empty set returns an empty result immediately, without running a query.
- New functions: `list_reviews_for_reviewer(session, user_id)`, `get_project_ids_for_manager(session, user_id)`, `set_projects_for_manager(session, user_id, project_ids)` (which replaces the whole set), and `get_project_ids_for_managers(session, user_ids)` (a bulk lookup for the Users list).

### Endpoint rules

- **Lists:** `GET /api/projects`, `GET /api/reviews`, `GET /api/reviews/years` and `GET /api/projects/{id}/reviews` are filtered by `visible_project_ids`.
- **Single-review access** (`GET /api/reviews/{id}`, `/download`, `/progress`):
  - Allowed when the review's project is visible to the user, or when `review.reviewer_id == user.id`.
  - Otherwise the response is **404**, not 403, so review IDs can't be probed.
  - A review with no project (`project_id IS NULL`) counts as visible only to `dashboard.view_all` and to its assigned reviewer.
  - Progress for an in-memory review that hasn't been saved yet stays limited to `reviews.create`.
- **`PATCH /api/reviews/{id}`:** allowed with `reviews.edit`, or with `reviews.finalize_own` when the user is the assigned reviewer. Otherwise it returns 404 if the user can't see the review, and 403 if they can see it but can't edit it.
- **`PATCH /api/reviews/{id}/reviewer`:** requires `reviews.assign_reviewer`. Today any signed-in user can do this; that is now restricted.
- **`GET /api/reviewers`:** returns active users whose role has `reviews.finalize_own` (reviewer, management and admin), with `id`, `email` and `name`.
- **New `GET /api/my/reviews`** (requires `my_reviews.view`): reviews where `reviewer_id` is the current user, newest first, in the same row shape as `GET /api/reviews`.
- **Users API** (`users.manage`):
  - `GET /api/users` includes `name` and, for PMs, `project_ids`.
  - `POST` and `PATCH` accept `name`.
  - Unknown roles get **400**, as today.
  - New `PUT /api/users/{id}/projects` with body `{project_ids: [...]}` replaces the assignment set. It returns 404 for an unknown user or project, and 400 if the user isn't a `project_manager`.
  - Changing a PM's role to anything else deletes their assignments.
- **Chatbot (`POST /api/chat`):** requires `chat.use`. `build_agent` receives `visible_project_ids`, and the `query_reviews` tool adds the filter to every query in code, so the restriction doesn't depend on the prompt. If a PM has no projects, the tool returns no rows.
- **`GET /api/auth/me`:** adds `name`, `home_path` and `permissions` (the list of capability keys the user holds), so the frontend mirrors the backend without hard-coding role names.
- **Settings router:** `settings.manage`. **Ollama models:** `reviews.create` or `settings.manage`.

## Frontend design

### Shared navbar: `components/AppNav.jsx` (replaces `TopNav` and `NavActions`)

- **Left side:** the logo mark and "CodeAssure" (linking to the role's home page), then `NavLink`s filtered by permission. The active link is underlined in brand coral.
  - **Dashboard:** shown for `dashboard.view_all` or `dashboard.view_assigned`.
  - **My reviews:** `my_reviews.view`.
  - **Cycles:** coordinators only (placeholder in Part 1).
  - **Users:** `users.manage`.
- **Right side:**
  - **Avatar:** a circular button showing initials, taken from `name` or from the part of the email before the @. The name appears next to it, with the role underneath in smaller muted text. The text collapses to the avatar alone below 640px.
  - **Avatar menu:** Settings (if `settings.manage`) and Users (if `users.manage`), then a divider and Log out. It closes on Esc and on a click outside, returns focus to the avatar button, and uses `aria-haspopup` and `aria-expanded`.
- **Size and spacing:** the bar is 56px high, all icons are 20px, items are spaced evenly, and nothing wraps or overflows at common widths.
- **Removed:** the "← Home" link, and the dashboard page's separate copy of the nav markup.

### Routing and guards

- `RouteGuards.jsx` gains `RequirePermission({ permission | anyOf })`. It redirects to the user's `home_path` when the user lacks the permission.
- `/` goes to the dashboard when the user can see one, and otherwise redirects to `home_path`.
- **Guarded routes:**
  - `/review/:platform`: `reviews.create`
  - `/settings`: `settings.manage`
  - `/users`: `users.manage`
  - `/my-reviews`: `my_reviews.view`
  - `/cycles`: coordinator
  - `/reviews/:id` (report page): any signed-in user. The backend decides whether to return 404.
- `AuthContext` exposes `permissions`, `homePath`, and a `can(permission)` helper.

### Pages

- **My reviews (`pages/MyReviewsPage.jsx`, new):**
  - A table with project, platform, date, AI score, status and an "Open" action.
  - A **Pending** / **All** toggle, defaulting to Pending, where Pending means any status other than `approved`.
  - Empty state: "No reviews assigned to you."
- **Dashboard (`ProjectDashboardPage`):** the same page. Actions are shown or hidden by permission:
  - Start review and Upload need `reviews.create`.
  - Rename needs `projects.rename`.
  - Delete needs `reviews.delete`.
  - The chatbot needs `chat.use`.
  - A PM with no projects sees: "No projects assigned yet — contact your admin."
- **Report page:**
  - Edit controls show when the user has `reviews.edit`, or has `reviews.finalize_own` and is the assigned reviewer.
  - The reviewer picker shows only with `reviews.assign_reviewer`.
  - Delete shows only with `reviews.delete`.
- **Users page:**
  - The role dropdown offers all five roles with readable labels, plus an editable Name column.
  - When the role is `project_manager`, a **searchable multi-select of projects** appears (checkbox list with chips for selected items, built on `SearchableSelect`) and saves through `PUT /api/users/{id}/projects`.
- **Cycles (`pages/CyclesPlaceholderPage.jsx`, new):** a card reading "Quarterly review cycles are coming soon."

### Visual polish limits

- The navbar is fully restyled.
- Alignment and spacing are fixed on the dashboard header row and the Users table.
- A whole-app UI review is planned after Part 2.

## Error handling

- **403:** the user lacks a capability for something they can see. **404:** the user can't see the resource.
- **400:** unknown role, or assigning projects to a non-PM.
- The frontend's existing 401 handling redirects to login. A 403 from a guarded action shows "You don't have permission to do this." A 404 on the report page shows "Review not found."

## Testing

**Backend (pytest):**
- A test generated from a table checks every role × capability against `PERMISSIONS`.
- `visible_project_ids` is checked for each role, including a PM with no projects.
- **Scoped endpoints:**
  - The list endpoints return only the PM's projects.
  - Detail, download and progress return 404 outside the PM's projects.
  - The assigned reviewer can open a review outside any visible project.
- **Reviewer edits:**
  - The assigned reviewer's PATCH succeeds.
  - A reviewer who isn't assigned gets 404 or 403.
  - A reviewer can't reassign.
- Coordinators get empty or 403 responses from dashboard endpoints and 403 from chat.
- The chatbot `query_reviews` tool never returns rows outside the scope.
- **Users API:**
  - Project assignment replaces the set, and unknown projects return 404.
  - Changing a PM's role clears their assignments.
  - Unknown roles return 400, and `name` round-trips.
- **Migration:** `user` becomes `project_manager`, and the downgrade path works.

**Frontend (Jest + React Testing Library):**
- `AppNav`: the links for each role, the active state, the avatar initials, and keyboard open and close of the menu.
- `RequirePermission`: redirects to `home_path`, and `/` sends each role to its home page.
- `MyReviewsPage`: rows, the Pending/All filter, and the empty state.
- Dashboard: PMs don't see actions they lack, and the "no projects" message shows.
- Users page: the project multi-select appears only for PMs, and saving sends the right IDs.
- Existing tests that used `user` or the old reviewer behaviour are updated.

**Manual Docker smoke test:**
- Read the existing users and settings before writing anything.
- Create one account per role and check each home page and what each can see.

## Out of scope / deferred to Part 2–3

- Per-project platform lists and the "one review per platform per quarter" completion rule.
- The Coordinator's cycles UI, PM DevOps URL entry, the org-wide PAT in Settings, and autonomous execution.
- Saving review progress in the database.
- Emails and reminders.

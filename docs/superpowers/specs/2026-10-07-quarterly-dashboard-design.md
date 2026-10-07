# Quarterly Dashboard & Cycle Initiation (Part 2, slice 1) — Design Spec

**Date:** 2026-10-07
**Status:** Approved in brainstorming
**Branch:** `quarterly-cycles`, stacked on `roles-and-access` (Part 1)

## Context

Part 1 (`2026-10-07-roles-and-access-design.md`) added the coordinator role. Code reviews happen quarterly: a project's quarter is **done** only when every platform it has received at least one review in that quarter. This slice gives coordinators a dashboard of each project's quarterly status, and lets them **start** a quarter's review by assigning a reviewer to each platform.

Later Part 2 slices add the rest of the workflow on top of the tables introduced here:
- the PM enters a DevOps URL for each platform;
- the org-wide PAT is stored in Settings;
- the review runs on its own;
- the stage tracker shows progress, and review progress is saved in the database.

Part 3 adds emails.

## Goals

- Each project has an explicit list of the **platforms** it has. Existing projects get theirs backfilled from past reviews.
- A **quarterly dashboard** shows one row per project and four quarter cards for the selected year, each tinted by status.
- Coordinators (and admins and Management) can **initiate** a quarter for a project, assigning a reviewer to each platform.
- The coordinator's home page becomes this dashboard, with **Projects** as a separate nav item.

## Non-goals (this slice)

- PM DevOps URL entry, the org PAT, running reviews automatically, and stage timestamps or reminders (later Part 2 slices).
- Emails (Part 3).
- Editing or cancelling a cycle once it's started.

## Platforms

- **Tracked platforms:** `Android`, `iOS`, `.NET`, which are the `label`s of the platforms marked available in `frontend/src/platforms.js`. These match `platform_reviews.platform` values.
- The backend constant `TRACKED_PLATFORMS = ("Android", "iOS", ".NET")` validates input.
- Any platform comparison against `platform_reviews.platform` is case-insensitive.

## Data model (one Alembic migration, down_revision `b7c8d9e0f1a2`)

- **`project_platforms`:** `project_id` → `projects.id` (ON DELETE CASCADE), `platform` String. Primary key `(project_id, platform)`.
- **`review_cycles`:**
  - Columns: `id` String PK, `project_id` → `projects.id` (ON DELETE CASCADE), `year` Integer, `quarter` Integer (1–4), `initiated_by` → `users.id` (nullable, ON DELETE SET NULL), `initiated_at` DateTime(tz).
  - Unique `(project_id, year, quarter)`.
- **`review_cycle_assignments`:**
  - Columns: `cycle_id` → `review_cycles.id` (ON DELETE CASCADE), `platform` String, `reviewer_id` → `users.id` (nullable, ON DELETE SET NULL).
  - Primary key `(cycle_id, platform)`.
- **Backfill:** for each project, insert one `project_platforms` row for each distinct tracked platform among its reviews where `status <> 'error'`. Platform names are matched case-insensitively and stored in their canonical label form.
- **Downgrade:** drop the three tables.
- **Project deletion:** a project with reviews still can't be deleted (Part 1). A project with no reviews can have platforms and cycles, so `crud.delete_project` deletes `project_platforms`, cycle assignments and cycles explicitly before the project. SQLite tests don't enforce cascades.

## Quarter status (backend, pure function)

`quarter_status(project_created_at, platforms, covered_platforms, cycle_exists, year, quarter, today) -> str`. All dates are in **UTC**.

- **Quarter dates:** Q1 runs Jan 1–Mar 31, Q2 Apr 1–Jun 30, Q3 Jul 1–Sep 30, and Q4 Oct 1–Dec 31. A quarter **has ended** when `today` is after its last day.
- **Covered:** a platform is covered when at least one review of the project on that platform has `status <> 'error'` and `created_at` within the quarter.

The rules are checked in this order:

| Status | Rule |
|---|---|
| `not_applicable` | The quarter ended before the project's **tracked-since** date: the earlier of `projects.created_at` and its first non-errored review. Historical sheets are often uploaded after the project record exists |
| `done` | The project has at least one platform, and every one is covered |
| `overdue` | The quarter has ended and it isn't done |
| `in_progress` | The quarter has started (today is on or after its first day), and either a cycle exists or at least one platform is covered |
| `not_started` | Anything else: a future quarter, or the current quarter with no cycle and no coverage |

A project with **no platforms** is returned with `platforms: []` and no quarter statuses. The UI shows a prompt instead of cards.

## Capabilities (extends `app/auth/permissions.py`)

- `cycles.view`: admin, Management, coordinator.
- `cycles.initiate`: admin, Management, coordinator.
- **`projects.rename` is renamed to `projects.edit`** (same roles). It now covers both the name and the platforms. All usages are updated on the backend, the frontend and in `testUtils/authUsers.js`.
- **Home paths:** the coordinator's changes from `/projects` to `/`.

## API

- **`GET /api/quarterly?year=YYYY`** (`cycles.view`) returns:

  ```json
  {"year": 2026, "today": "2026-10-07", "projects": [{
     "id", "name", "platforms": ["Android", ".NET"],
     "quarters": [{
        "quarter": 1, "start": "2026-01-01", "end": "2026-03-31",
        "status": "done|in_progress|overdue|not_started|not_applicable",
        "covered": [{"platform": "Android", "review_id": "...", "reviewed_at": "..."}],
        "missing": ["iOS"],
        "can_initiate": true,
        "cycle": null | {"id", "initiated_at", "initiated_by_name", "assignments": [{"platform", "reviewer_id", "reviewer_name"}]}
     }, ... four entries ...]
  }]}
  ```

  - `covered` lists the latest qualifying review for each platform.
  - `can_initiate` is true when the status is `in_progress`, `not_started` or `overdue`, no cycle exists, and the quarter has started.
  - Projects are sorted by name.
  - `year` defaults to the current UTC year.

- **`PUT /api/projects/{id}/platforms`** with body `{platforms: [...]}` (`projects.edit`) replaces the set and returns the project dict. It returns 404 for an unknown project and 400 for a platform outside `TRACKED_PLATFORMS`. `GET /api/projects` and the other project responses include `platforms` (sorted).
- **`POST /api/projects/{id}/cycles`** with body `{year, quarter, assignments: [{platform, reviewer_id}]}` (`cycles.initiate`):
  - Returns 404 for an unknown project.
  - Returns 400 when:
    - the project has no platforms;
    - the assignment platforms don't exactly match the project's platforms;
    - any reviewer isn't an active user whose role holds `reviews.finalize_own`;
    - the quarter can't be started (it hasn't started yet, or it's done or `not_applicable`).
  - Returns **409** "This quarter's review has already been initiated." if a cycle exists.
  - On success it returns the quarter entry, in the same shape as `GET /api/quarterly`.

## Frontend

- **Navigation (`AppNav`):**
  - A user with `dashboard.view_*` sees "Dashboard" → `/` (the scores dashboard).
  - A user with only `cycles.view` (the coordinator) sees "Dashboard" → `/`, which renders the quarterly dashboard.
  - Admins and Management also get **"Quarterly"** → `/quarterly`.
  - "Projects" stays for `projects.view`.
- **Routing:**
  - `/` shows the scores dashboard if the user can see one. Otherwise it shows the quarterly dashboard if they have `cycles.view`. Otherwise it redirects to `home_path`.
  - `/quarterly` requires `cycles.view`.
- **`QuarterlyDashboardPage`:**
  - **Header:** the title "Quarterly reviews", a year select (current year and the previous two, plus any year from `/api/reviews/years`) and a project search box.
  - **One row per project:** the name and platform tags on the left, then the four `QuarterCard`s in a grid (4 columns, 2 below 900px, 1 below 520px).
  - **Projects with no platforms:** the row shows "Set platforms to track quarterly reviews" with a link to `/projects`.
- **`QuarterCard`:**
  - **Contents:**
    - "Q3 · Jul–Sep" and a status badge (Done, In progress, Overdue, Not started, N/A).
    - One line per platform: ✓ with the review date if covered, ○ if missing.
    - If a cycle exists: "Initiated {date} by {name}" and the reviewer for each platform.
    - An **Initiate review** button, shown when `can_initiate` and the user has `cycles.initiate`.
  - **Tints:**
    - **Done:** a green tint, `color-mix(in srgb, #2e9e5b 12%, var(--color-bg))`.
    - **In progress:** a yellow tint, `color-mix(in srgb, #e0b400 16%, var(--color-bg))`.
    - **Overdue:** a coral tint, `color-mix(in srgb, var(--color-brand-coral) 12%, var(--color-bg))`.
    - **Not started:** `var(--color-bg)` (white) with a border.
    - **N/A:** `var(--color-surface)`, muted text.
  - Each status has a matching badge colour, and the status is always written out as text, so colour isn't the only signal.
- **`InitiateCycleDialog`:**
  - Shows the title "Initiate Q{n} {year} review — {project}" and one reviewer `<select>` per platform, listing options from `GET /api/reviewers` by name or email.
  - Submit stays disabled until every platform has a reviewer.
  - On success it replaces that quarter's card with the returned entry. On failure it shows the API's `detail`.
- **Projects page:**
  - A **Platforms** column with tags.
  - New project and Rename become a **project dialog** with name plus platform checkboxes (Android, iOS, .NET). Creating a project then calls `PUT /platforms`, and the edit dialog saves both the name and the platforms.
- **Permission checks** that used `projects.rename` now use `projects.edit`.

## Error handling

- The API returns 400, 404 and 409 as listed above. The frontend shows the `detail` text from the response in the dialog.
- If `GET /api/quarterly` fails, the page shows "Couldn't load quarterly status."

## Testing

**Backend:**
- `quarter_status`, table-driven with a fixed `today`:
  - each of the 5 states;
  - first and last day of a quarter;
  - a project created mid-year;
  - a project with no platforms, and with an empty covered set.
- Covered logic: errored reviews and reviews from other quarters don't count, and platform matching is case-insensitive.
- `GET /api/quarterly`: permissions, the response shape and `can_initiate`.
- `PUT /platforms`: validation and permissions.
- `POST /cycles`:
  - succeeds, and a second attempt returns 409;
  - mismatched platforms, an invalid reviewer, a done or future quarter, and a project with no platforms each return 400;
  - project managers and reviewers get 403.
- The migration backfill, tested by running the backfill SQL on SQLite with seeded reviews.
- The permission map test is updated (`projects.edit`, `cycles.*`, coordinator home `/`).

**Frontend:**
- `QuarterCard`: the badge and tint class for each state, the covered and missing lines, the cycle info, and when the Initiate button shows.
- `InitiateCycleDialog`: submit is disabled until every platform has a reviewer, it posts the right body, and it shows API errors.
- `QuarterlyDashboardPage`: rows, the no-platforms prompt, the year change refetching, and search.
- `AppNav` and routing: the coordinator lands on the quarterly dashboard at `/`; admins see the "Quarterly" link.
- Projects page: the platform checkboxes and the platforms column.

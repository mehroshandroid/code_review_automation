# Organization-Wide Phase 2: Project Dashboard Design Spec

**Status:** Approved
**Date:** 2026-08-07

## Purpose

Phase 2 of the org-wide initiative (branch `org-wide-phase1-db`, not yet merged
to master -- phases accumulate on this branch until the whole initiative
merges at the end). Phase 1 shipped Postgres persistence with zero visible UI
change. This phase builds the actual home-page experience the user
originally asked for: a project list, a per-project review-history
graph+table, and a way to start a new review scoped to a project -- plus a
gap the original ask assumed was already solved: a real way to view an
**already-completed, persisted** review's full report later, not just a
still-live one.

## 1. Backend API

Two new endpoints:

- `GET /api/projects/{project_id}/reviews` -- lightweight list for the
  overview: `id, platform, status, created_at, completed_at,
  total_score_pct` per review, newest first. Not the full report.
- `GET /api/reviews/{review_id}` -- reads a single persisted row from
  Postgres (`app/db/crud.py` gains a `get_review_by_id`), returns
  `result_data` plus `status`, `platform`, `project_name`,
  `total_score_pct`, `llm_provider`, `created_at`, `completed_at`,
  `workbook_path` (as a boolean `has_workbook`, not the raw path). 404 if
  not found.

`GET /api/reviews/{id}/download` (existing) is extended: if `review_id`
isn't in the live in-memory `_reviews` dict (or has no `download_path`),
fall back to looking it up in Postgres and serving from its
`workbook_path` on the persistent artifacts volume instead of 404ing.

## 2. Routing & page restructuring

- `/` becomes the new project dashboard (`ProjectDashboardPage`),
  **replacing** the current platform-picker `HomePage.jsx`. Sidebar (project
  list, first project auto-selected) + left-wider section (graph + table) +
  right section (the existing platform-picker cards, relocated here,
  scoped to the selected project).
- `/projects` (phase 1's bare create/list page) is **retired** --
  `ProjectsPage.jsx` and its test file are deleted; its create-project
  form logic moves into the new dashboard's sidebar.
- New route `/reports/:reviewId` -- the read-only historical detail page.
  Deliberately named apart from `/review/:platform` (starting a *new*
  review), which is unchanged.
- `/review/:platform`'s platform-card click now passes the selected
  project's ID through via router state (`navigate(..., { state: {
  projectId } })`), read in `ReviewPage.jsx` and threaded down to
  `AndroidReviewFlow`'s `handleUpload`. This closes a real gap found during
  design: phase 1 added `projectId` to the *backend's* create-review
  endpoint, but the frontend's `createReview()` in `services/api.js` never
  actually sends it -- it gains a new `projectId` parameter now.

## 3. New/changed frontend components

- `ProjectDashboardPage.jsx` (new, replaces `HomePage.jsx` at `/`) --
  container: fetches projects via `getProjects()`, holds selected-project
  state (first project selected by default), renders the three-part layout.
  Empty state (zero projects) shows the create-project prompt directly,
  no sidebar/graph/table to show yet.
- `ProjectSidebar.jsx` (new) -- project list (click to select) + "+ New
  project" form, porting the create logic from the retired
  `ProjectsPage.jsx`.
- `ProjectReviewHistory.jsx` (new) -- fetches
  `GET /api/projects/{id}/reviews`; renders a Recharts `LineChart` (one
  line per platform, X=date, Y=`total_score_pct`) above a table (date,
  platform, status badge, score). Reuses Recharts for consistency with the
  existing `CategoryScoresChart.jsx`. Each row navigates to
  `/reports/:id`. Empty state (project has zero reviews yet) shows a plain
  message, no empty chart.
- The right section's platform cards are the existing markup from
  `HomePage.jsx`, relocated into `ProjectDashboardPage.jsx`.
- `ReviewReportPage.jsx` (new) -- fetches `GET /api/reviews/:reviewId`
  once on mount (no polling -- it's a finished record), renders the
  existing `ReportTable` component fed from the fetched data, a
  findings-style summary (warning/secret/lint counts from `result_data`),
  a status badge, and a download link (using the extended download
  endpoint). 404 from the API shows a simple "review not found" state.

## 4. Testing

- Backend: `test_projects_api.py` gains coverage for
  `GET /api/projects/{id}/reviews`. New `test_review_detail_api.py` for
  `GET /api/reviews/{id}` (found + 404). Extend the existing download-endpoint
  tests for the fallback-to-persisted-workbook path.
- Frontend: `ProjectDashboardPage.test.jsx` (sidebar selection, empty
  state), `ProjectReviewHistory.test.jsx` (graph/table rendering, row-click
  navigation), `ReviewReportPage.test.jsx` (fetch + render + download
  link + 404 state), updated `api.test.js` for `projectId` threading and
  the two new endpoints. `ProjectsPage.jsx`/`ProjectsPage.test.jsx` deleted.

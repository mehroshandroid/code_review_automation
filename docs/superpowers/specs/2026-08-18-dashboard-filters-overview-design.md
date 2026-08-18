# Dashboard Filters & Overview Redesign: Design Spec

**Status:** Approved
**Date:** 2026-08-18
**Branch:** `chatbot-langchain-review-insights` (continuing on this branch per the user's direction for recent unrelated dashboard changes)

## Purpose

Replace the main dashboard's project-sidebar-driven, single-project view with an org-wide filter bar (Year / Platform / Project) plus an aggregate overview (radial score rings) and a results table listing every review matching the current filters. Lets the org see e.g. "2026, Android, Moove project health" — or broader slices like "all Android reviews in 2026 across every project" — in one screen, instead of only ever viewing one project at a time.

## Scope

**In scope:** the main dashboard's layout, filtering, aggregate visualization, and results table. The "start a new review" flow is relocated (not redesigned) into a dialog. The LLM-provider picker is relocated into that same dialog.

**Out of scope:** the review flow itself (`AndroidReviewFlow.jsx`, `UploadForm.jsx`, etc.), the report page (`ReviewReportPage.jsx`), Settings, and the chatbot — none of these change.

**Terminology:** "domains" (user's term) = this app's existing `platform` field (Android/iOS/.NET/Web (React)) — no new data model needed. The reference screenshot's "Project Category" label maps to the same concept.

## Backend

**New endpoint:** `GET /api/reviews?year=<int>&platform=<str, optional>&project_id=<str, optional>` — org-wide, cross-project review listing (distinct from the existing per-project `GET /api/projects/{id}/reviews`, which is unchanged). `year` is always provided (the frontend never has an "all years" state). `platform`/`project_id` are optional; omitted means no filter on that dimension ("All"). Returns the same trimmed per-review shape already used by `GET /api/projects/{id}/reviews`: `id`, `project_id`, `project_name`, `platform`, `status`, `created_at`, `total_score_pct`, `category_scores: [{id, name, percent_points}]`. **Includes errored reviews** (shown in the results table, matching today's per-project table behavior) — the endpoint does no aggregation or exclusion beyond the explicit filters; it's a plain filtered list.

**New endpoint:** `GET /api/reviews/years` → `{"years": [2024, 2025, 2026]}`, the distinct years with any review data (`extract('year', created_at)`), sorted ascending — populates the Year dropdown's options accurately instead of a hardcoded range.

**No backend aggregation math.** The overview (average total score, per-category averages) is computed **client-side** from the same filtered list the table renders, mirroring how `ProjectReviewHistory.jsx` already computes its chart data client-side today. This keeps the new backend endpoint a simple filter, avoids a second aggregation code path to keep in sync with the first, and means one fetch serves both the overview and the table.

**Platform options** come from the existing frontend `PLATFORMS` constant — no backend endpoint needed, it's already a fixed known list. **Project options** come from the existing `GET /api/projects` — the searchable dropdown filters that list client-side (adequate at this app's scale; no new search endpoint).

## Frontend

### Layout

`ProjectDashboardPage.jsx` is restructured. **`ProjectSidebar.jsx` and `ProjectReviewHistory.jsx` (and their test files) are deleted outright**, not refactored or reused — their create/rename dialog markup is relocated (copied, then the originals deleted) into the new filter bar and "start review" dialog as noted below; their chart/table logic isn't reused since the new components work over a differently-shaped, org-wide (not single-project) dataset. **New top-to-bottom layout:**

1. **Filter bar** (`DashboardFilters.jsx`, new): three single-select **searchable dropdowns** — Year, Platform, Project — plus a **Reset** button restoring defaults (current year, "All platforms", "All projects"). Built on one reusable primitive, `SearchableSelect.jsx` (type-to-filter text input + option list, using existing `.input`/`.card` design-system classes, no new dependency), used for all three with different option lists.
   - **Year:** options = `GET /api/reviews/years` result; default = current calendar year (selected even if that year has no data yet — matches "by default current year... selected").
   - **Platform:** options = `PLATFORMS` labels + a leading "All platforms" entry; default = "All platforms".
   - **Project:** options = `GET /api/projects` results (searchable by name) + a leading "All projects" entry; default = "All projects". Includes an **"+ Add new project"** entry (opens the same create-project dialog `ProjectSidebar.jsx` has today, relocated here verbatim rather than duplicated — `ProjectSidebar.jsx` is deleted once this replaces it). When a specific project (not "All") is selected, a small edit/pencil affordance next to the dropdown opens the same rename dialog, also relocated from `ProjectSidebar.jsx`.
2. **Overview** (`DashboardOverview.jsx`, new): see below.
3. **Results table** (`DashboardResultsTable.jsx`, new): every review matching the current filters, across every matching project. Columns: Date, Project, Platform, Status, Score (adds a Project column vs. today's per-project table, since results can now span multiple projects). Rows are clickable, navigating to `/reports/:id`, unchanged from today.
4. **"Start review" button**: always visible near the filter bar, independent of current filter state. Opens a dialog: pick a project (reusing `SearchableSelect`, including "+ Add new project"), then pick a platform (reusing the existing platform-card grid from today's flow), then the LLM-provider picker (Azure/Ollama + model — relocated verbatim from the current sidebar's right panel; it's a `localStorage`-backed global preference, not tied to dashboard filter state). Selecting a platform card navigates to `/review/:platform` with `state: {projectId}`, exactly as today.

Any filter change (year/platform/project) refetches `GET /api/reviews` with the new params and recomputes the overview + re-renders the table from the new list. An empty filtered result set shows a message in place of the overview and table, matching the existing "No reviews yet" empty-state style.

### Overview visualization

`DashboardOverview.jsx`, built with Recharts `RadialBarChart` (no new charting dependency):

- **Final Score ring** (larger, prominent): average `total_score_pct` across all **non-error** reviews in the current filtered set. A "based on N reviews" caption underneath states how many reviews fed the average.
- **Per-category rings** (smaller grid beside/below the Final Score ring): one ring per distinct category `name` present across the filtered non-error reviews, valued as the average `percent_points` for that name across whichever of those reviews contain it. A category with zero occurrences in the current filtered set simply has no ring.
- Every ring is colored by its value — red `<60`, orange `60–79`, green `≥80` (a default matching the reference screenshot's traffic-light convention; adjustable later, not user-configurable in this pass) — with the percentage labeled in the ring's center and the category name captioned below it.

## Testing

- **Backend:** `GET /api/reviews` — filters by year (required), platform (optional), project_id (optional), includes errored reviews, returns the same trimmed shape as the per-project endpoint. `GET /api/reviews/years` — returns distinct years sorted ascending, empty list when no reviews exist.
- **Frontend:** `SearchableSelect.test.jsx` (type-to-filter, selecting an option, the default "All" entry, the custom "+ Add new project" slot) · `DashboardFilters.test.jsx` (all three selects wire to state, Reset restores defaults, any change triggers a refetch) · `DashboardOverview.test.jsx` (averaging math excluding errored reviews, color-threshold classification, the "based on N reviews" caption, empty-set behavior) · `DashboardResultsTable.test.jsx` (one row per review, Project column present, row click navigates to `/reports/:id`) · a "start review" dialog test (project + platform + provider selection navigates to the right `/review/:platform` route with the right state) · an integration test on the restructured `ProjectDashboardPage.jsx` (renders filters + overview + table together, a filter change re-fetches and updates all three).

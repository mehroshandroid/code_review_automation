# Organization-Wide Phase 1: Database & Project Persistence Design Spec

**Status:** Approved
**Date:** 2026-08-04

## Purpose

First of 5 planned phases toward making this an organization-wide tool: (1) DB +
data model + review persistence [THIS PHASE], (2) review status lifecycle
refinements, (3) new home page (project list sidebar + per-project dashboard
with graph+table), (4) org-wide settings page (LLM provider defaults,
sample-sheet defaults, per-platform/per-clause checklist CRUD -- replacing the
`CLAUSE_CHECKLISTS` dict in `llm_prompts.py`), (5) approval workflow.

Reviews are currently entirely ephemeral: an in-memory `_reviews: dict` in
`backend/app/api/reviews.py`, gone on backend restart, with no relation to any
"project" concept. This phase introduces Postgres, a `projects`/
`platform_reviews` schema, and persists every review to a `pending_approval`
(or `error`) row on completion -- with **zero visible change** to the existing
review flow's behavior, plus a minimal new page to create/list projects.

## 1. Schema & storage

```
projects
  id            text PK   (uuid4 string, matching existing review_id convention)
  name          text NOT NULL UNIQUE
  created_at    timestamptz

platform_reviews
  id                  text PK   (same review_id already generated today)
  project_id          text FK -> projects.id, NULLABLE
  platform            text      ("Android" | "iOS" | ".NET" | "Web (React)")
  status              text      ("pending_approval" | "approved" | "completed" | "error")
  project_name        text      (display name derived from zip/repo)
  created_at          timestamptz
  completed_at        timestamptz, nullable
  total_score_pct     numeric, nullable
  llm_provider        text
  llm_model           text, nullable
  compile_check_mode  text
  source              text      ("upload" | "devops")
  workbook_path       text, nullable
  result_data         JSON      (category_scores, warnings, secrets_found, lint_issues, compile_status, stats, error)
  created_by          text, nullable
  approved_by         text, nullable
  approved_at         timestamptz, nullable
```

`platform`/`status` are plain `text` (app-validated), not Postgres `ENUM`
types, since both are still evolving. `result_data` excludes `code_context`
and full `prompt_text` values (can run to 120,000 characters each; not needed
for the approval record) -- those stay ephemeral, exactly as today.

No `organizations` table this phase (single implicit org until real
auth/SSO exists).

## 2. DB access & infrastructure

SQLAlchemy 2.0 (async engine + `asyncpg` driver) + Alembic migrations. IDs
stay plain `text` columns (not native Postgres `UUID`) so the same models
work against SQLite in tests without a dialect split.

New `backend/app/db/`:
- `models.py` -- `Project`, `PlatformReview` ORM models
- `session.py` -- async engine/sessionmaker, `get_db_session()` for use
  outside FastAPI's request-scoped DI (the review pipeline runs as a
  background task, not inside a request)
- `crud.py` -- `create_project`, `list_projects`, `persist_review_result`

`docker-compose.yml` gains:
- `postgres` service (official `postgres:16` image, `postgres-data` volume)
- `review-artifacts` volume, mounted into `backend` at `/data/reviews`
- `backend` gets `DATABASE_URL` env var + `depends_on: postgres`

Alembic migrations run automatically on backend container startup (`alembic
upgrade head` before `uvicorn`, via the Dockerfile's `CMD`).

## 3. API changes & persistence-on-completion

New endpoints in a new `backend/app/api/projects.py`:
- `POST /api/projects` -- body `{name}`, creates and returns a project.
  404/409-appropriate error if the name already exists (unique constraint).
- `GET /api/projects` -- lists all projects, newest first.

`POST /api/reviews` (existing create-review endpoint) gains an **optional**
`project_id` form field. Omitted -> `null`, identical behavior to today.

`_run_review()`'s two terminal points gain an additive persistence step,
with the existing in-memory `_reviews` dict and its 2-second-poll behavior
**completely unchanged** (no regression risk to the live progress UX):
- **Success path** (after `state["status"] = "completed"` is set): copy
  `output.xlsx` from the temp work dir to the persistent
  `/data/reviews/{review_id}.xlsx` path (survives the temp dir's cleanup),
  then insert a `platform_reviews` row with `status="pending_approval"`,
  `workbook_path` set, and `result_data` built from the trimmed state dict
  (category_scores, warnings, secrets_found, lint_issues, compile_status,
  stats -- not code_context/prompt_log).
- **Error path**: insert a row with `status="error"`, `result_data={"error":
  <message>}`, no workbook.

A DB write failure at either point is logged but does not change the
in-memory review's outcome shown to the current user -- persistence is
best-effort additive, not a hard dependency of the existing flow succeeding.

Out of scope this phase (deferred to phase 5, no UI would use it yet): a
"download a persisted review's workbook by ID" endpoint serving from
`workbook_path` rather than the temp dir.

## 4. Frontend: minimal project affordance

New route `/projects` (added alongside the existing `/` and `/review/:platform`
routes -- the current home page is completely unchanged). A single new page:
a text input + "Create" button (`POST /api/projects`) and a plain list of
existing projects below (`GET /api/projects`) -- no graph, no table, no
sidebar layout; that's phase 3. Reuses existing design-system classes
(`.card`, `.btn`, `.input`) for visual consistency. A "Projects" link is
added to `TopNav` so the page is reachable.

## 5. Testing

- **DB-layer tests** (`test_db_models.py`/`test_crud.py`): run against an
  in-memory SQLite database (`sqlite+aiosqlite:///:memory:`) using
  SQLAlchemy's dialect-generic `JSON` type -- keeps the entire test suite
  fast and dependency-free (no live Postgres required), matching this
  project's established pattern of not requiring external services for
  `pytest tests/` to pass. Production still uses real Postgres via
  `DATABASE_URL`.
- **Projects API tests** (`test_projects_api.py`): standard FastAPI
  TestClient tests against the SQLite-backed test DB.
- **`reviews.py` tests**: extend existing `test_reviews_create.py` /
  `test_reviews_integration.py` with monkeypatched `crud.persist_review_result`
  (mirroring the existing pattern already used for `check_compile_warnings`/
  `score_category`), asserting it's called with the right status/data on
  both the success and error paths -- no real DB needed for these.
- **Frontend**: new `ProjectsPage.test.jsx` (create + list), extend
  `TopNav.test.jsx` for the new link.

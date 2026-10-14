# Bulk Quarter Initiation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start a quarter for all eligible projects at once, with one digest email per PM and per reviewer.

**Spec:** `docs/superpowers/specs/2026-10-12-bulk-quarter-initiation-design.md`

**Architecture:**
- **Shared helper:** `_initiate_one(session, project, year, quarter, assignments, user)` in `app/api/quarterly.py` holds single-project validation and creation. It raises `HTTPException`, is used by the existing single endpoint (which keeps its per-project emails) and by the new bulk endpoint (which catches the exception per project and sends digests at the end).
- **Templates:** two new events, `cycles_initiated_digest` and `reviewer_assigned_digest`, in `app/email/templates.py`.
- **Frontend:** a `BulkInitiateDialog` component and a button on `QuarterlyDashboardPage`.

**Commands:**
- Backend: `cd backend && venv/bin/python -m pytest -q`.
- Frontend: `cd frontend && CI=true npx react-scripts test --watchAll=false`.

## Review Focus

1. **A PM with three started projects** gets exactly one email listing all three. Nobody gets per-project emails from a bulk run. *Test: `test_bulk_sends_one_digest_per_pm_and_reviewer`.*
2. **One project failing** (already initiated in between) doesn't stop the others. *Test: `test_bulk_projects_succeed_or_fail_independently`.*
3. **Pre-fill never suggests** an inactive or demoted reviewer. *Test: `test_preview_prefills_reviewers_from_last_cycle_only_if_still_valid`.*
4. **"Set for all"** never overwrites a reviewer already chosen. *Test: "set for all fills only empty slots".*
5. **Mixed results:** the results summary shows both started and skipped projects. *Test: "shows the results summary".*

## Task 1: Backend: shared initiation helper, preview, bulk endpoint, digest templates

- [ ] Write the failing tests in `backend/tests/test_bulk_initiate.py`:
  - **Preview:**
    - `test_preview_lists_eligible_and_skipped_with_reasons`
    - `test_preview_prefills_reviewers_from_last_cycle_only_if_still_valid`
  - **Bulk initiate:**
    - `test_bulk_initiate_starts_projects_and_returns_results`
    - `test_bulk_projects_succeed_or_fail_independently`
    - `test_bulk_sends_one_digest_per_pm_and_reviewer`
  - **Permissions and input:**
    - `test_bulk_is_forbidden_without_cycles_initiate`
    - `test_bad_quarter_is_400`
- [ ] Add template tests for the two digest subjects in `backend/tests/test_email_config_templates.py`.
- [ ] Run them and watch them fail.
- [ ] Implement:
  - `_initiate_one`, refactoring `initiate_cycle` to use it;
  - `_last_cycle_reviewers`, using the new crud function `get_latest_cycle_assignments(session, project_ids)`;
  - `bulk_preview` and `bulk_initiate`;
  - the digest templates.
- [ ] Run the full suite until it passes, then commit.

## Task 2: Frontend: dialog and button

- [ ] Write the failing tests in `frontend/src/components/BulkInitiateDialog.test.jsx`:
  - pre-fill
  - "set for all fills only empty slots"
  - the Initiate button disabled until complete
  - the posted body
  - "shows the results summary"
  - the skipped list
- [ ] Add a test to `QuarterlyDashboardPage.test.jsx`: the button shows only with `cycles.initiate` and only for the current year.
- [ ] Implement the API functions `getBulkPreview` and `bulkInitiate`, the dialog, and the button. Then run the suite and commit.

## Task 3: Smoke test and progress log

- [ ] Back up and rebuild, check the queue is idle, and pause it during the test.
- [ ] Preview with real data (read-only).
- [ ] Bulk-initiate only throwaway smoke projects, check the outbox digests, clean up, and resume the queue.
- [ ] Update `progress.md` and commit.

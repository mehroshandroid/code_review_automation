# Bulk Quarter Initiation — Design Spec

**Date:** 2026-10-12
**Status:** Approved in brainstorming (from demo feedback)
**Branch:** `bulk-initiate`, stacked on `nonblocking-pipeline`

## Goal

Coordinators can start a quarter's review for **all eligible projects at once**, instead of clicking Initiate on every card. Each PM and each reviewer receives **one digest email** for the whole batch.

## Decisions

- **Button:** "Initiate quarter for all projects", placed next to *Search projects* on the quarterly dashboard. It needs `cycles.initiate` (admin, management, coordinator) and appears only for the current year.
- **Quarters offered:** the current quarter (the default) and any earlier quarter of the current year that can still be initiated (catch-ups).
- **Reviewers:** each project's reviewers are pre-filled from that project's most recent cycle, using an assignment's reviewer only if that user is still an active reviewer, management or admin account. "Set for all" per platform fills only *empty* slots. Every ticked project must have a reviewer for each platform.
- **Each project succeeds or fails on its own.** A failure (for example, someone else just started it) skips that project and reports why.
- **Digests:**
  - Each PM of a started project gets **one** `cycles_initiated_digest` listing their started projects.
  - Each reviewer gets **one** `reviewer_assigned_digest` listing their project and platform assignments.
  - Starting a single project from its card still sends the per-project `cycle_initiated` and `reviewer_assigned` emails.

## API (`app/api/quarterly.py`, `cycles.initiate`)

- **`GET /api/quarterly/bulk-preview?year=Y&quarter=Q`** returns:

  ```text
  {year, quarter,
   eligible: [{project_id, project_name, platforms, managers: [{id, name}],
               suggested_reviewers: {platform: reviewer_id|null}}],
   skipped:  [{project_id, project_name, reason}]}
  ```

  - **Eligible** means `can_initiate` is true for that quarter.
  - **Skip reasons:**
    - "Already initiated"
    - "Already done this quarter"
    - "No platforms set"
    - "Not tracked yet that quarter"
    - "Quarter hasn't started"
  - **400** for a quarter outside 1–4.
- **`POST /api/quarterly/bulk-initiate`** with body `{year, quarter, projects: [{project_id, assignments: [{platform, reviewer_id}]}]}` returns `{results: [{project_id, project_name, status: "started"|"skipped", reason}]}`.
  - It uses the same validation as single initiation.
  - It sends the digests once, at the end.

## Frontend

- **`BulkInitiateDialog`:**
  - a quarter select;
  - an eligible-projects table: a tick box, project, PM chips, one reviewer select per platform cell, and a "No PM assigned — nobody will be emailed" warning;
  - "Set for all" per platform column;
  - a "Not included" list of skipped projects with reasons;
  - an **Initiate N projects** button, disabled until complete;
  - a results summary, after which the dashboard reloads.

## Testing

**Backend:**
- **Preview:** eligibility, the skip reasons, and the reviewer pre-fill (including ignoring inactive reviewers).
- **Bulk initiate:** starts the valid projects, skips invalid ones with reasons, and each project succeeds or fails on its own.
- **Digests:** exactly one per PM and one per reviewer, with the correct lists, and no per-project emails from a bulk run.
- **Permissions.**

**Frontend:**
- the dialog renders the pre-fill;
- "Set for all" fills only empty slots;
- Initiate stays disabled until complete;
- the posted body is correct;
- the results summary;
- the button is shown only with permission and only for the current year.

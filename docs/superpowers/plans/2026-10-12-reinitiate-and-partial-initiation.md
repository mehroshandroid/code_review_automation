# Reinitiate and Partial Initiation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Test-first throughout.

**Goal:** a platform can get a new round after approval (with a review count and history); a quarter can start with only some platforms and the rest added later; the queue's Stop button stands out.

**Spec:** docs/superpowers/specs/2026-10-12-reinitiate-and-partial-initiation-design.md

**Commands:**
- Backend: `cd backend && venv/bin/python -m pytest -q`
- Frontend: `cd frontend && CI=true npx react-scripts test --watchAll=false`

## Global Constraints
- Every existing route, the worker, the stage tracker and reminders keep using the single assignment row per (cycle, platform).
- Quarter status rules don't change.
- New user-facing strings exactly as in the spec.

## Review Focus
- Reinitiate on a platform whose review is queued or running, or that is mid-re-run, must be refused.
- A zip source left on disk when a round resets must be deleted.
- Coverage: a round 1 review must stay counted for the cycle's quarter after round 2 starts, even though the assignment no longer points at it.
- Adding platforms to a cycle racing a second add of the same platform must give 409, not 500.
- Bulk digests when a project is added partially, and project deletion with rounds present.

## Task 1: Backend — partial initiation and adding platforms
- Tests (test_quarterly_api.py, test_bulk_initiate.py): subset create; add to an existing cycle; 409 duplicate; foreign platform 400; add refused before the quarter starts; `uninitiated_platforms` and `can_add_platforms`; email payload carries platforms; bulk preview lists partial projects with only their missing platforms; empty assignments give "No platforms selected"; the PM digest carries `projects: [{name, platforms}]`.
- Implementation: `_initiate_one` handles create vs add; `crud.add_cycle_assignments`; entry fields; templates.

## Task 2: Backend — rounds and reinitiate
- A migration adds `round` and `review_cycle_rounds`.
- Model plus crud: `archive_round`, `list_rounds`, `reset_assignment_for_new_round`. The deletion path is updated, and `list_cycle_review_ids` includes round reviews.
- `_quarter_entries` links the newest of the current review and the round reviews.
- The assignment dict gains `round`, `approved_rounds`, `can_reinitiate` and `history`.
- `POST .../reinitiate` with its emails, and the `cycle_reinitiated` template plus the round suffix.
- Tests in test_reinitiate.py.

## Task 3: Frontend
- InitiateCycleDialog: tick boxes and add mode.
- QuarterCard: "Not started", "Initiate remaining" and the review count.
- ManageCycleDialog: the reinitiate form, history, and the per-platform Initiate.
- BulkInitiateDialog: partial slots.
- QueuePage: the Stop icon.
- api.js: `reinitiateAssignment`.
- Tests for each.

## Task 4: Migration on Docker, smoke test with throwaway projects only, progress.md, final review

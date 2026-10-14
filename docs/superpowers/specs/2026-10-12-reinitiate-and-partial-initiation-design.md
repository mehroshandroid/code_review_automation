# Reinitiate a Platform and Partial Initiation — Design Spec

**Date:** 2026-10-12
**Status:** Design approved in brainstorming
**Branch:** `reinitiate-partial`, stacked on `bulk-initiate`

## Context

Demo feedback asked for three things:

1. **Reinitiate.** A platform's quarterly review can't be started again after it's approved. The ask is to allow a new round, and to show how many reviews a platform has had.
2. **Partial initiation.** Initiating currently requires a reviewer for every platform. The ask is to start only some platforms, and the rest later.
3. **Queue Stop.** The Stop action in the queue should stand out more.

## Decisions

- **Reinitiate means a new round after approval.** It's only offered when the platform's current review is **approved**. Before approval, the existing **Re-run** is the tool.
- **Rounds are stored as history (approach A).** The single assignment row per `(cycle, platform)` stays the *current round* and gains a `round` number. Finished rounds are copied into a new history table, so every existing route, the worker, the stage tracker and reminders keep working unchanged.
- **Partial initiation:** a cycle can start with any non-empty subset of the project's platforms. Missing platforms are added to the same cycle later.
- **Bulk:** an empty reviewer slot means "leave this platform for later". A ticked project needs at least one platform filled.
- **Quarter status rules are unchanged.** A reinitiated platform still counts as covered by its earlier approved round, so the quarter stays green.

## Data model (one migration)

**`review_cycle_assignments` gains:** `round`, an Integer, not null, server default `1`.

**New table `review_cycle_rounds`** (the history of finished rounds):

| Column | Notes |
|---|---|
| `id` | String PK (uuid) |
| `cycle_id` | FK `review_cycles.id`, `ondelete=CASCADE` |
| `platform` | String |
| `round` | Integer |
| `review_id` | FK `platform_reviews.id`, `ondelete=SET NULL`, nullable |
| `reviewer_id` | FK `users.id`, `ondelete=SET NULL`, nullable |
| `approved_at` | DateTime(tz), nullable |
| `archived_at` | DateTime(tz), not null |
| `archived_by` | FK `users.id`, `ondelete=SET NULL`, nullable |

- There is a unique constraint on `(cycle_id, platform, round)`.
- `crud.delete_project` also deletes the project's rounds explicitly, because SQLite doesn't enforce the CASCADE.

## Coverage

`crud.list_cycle_review_ids` also returns `review_cycle_rounds.review_id`. So an earlier round's review counts for its cycle's quarter, not for the date it ran.

For each `(cycle, platform)`, `_quarter_entries` links the **latest review** among the current round's review and the archived rounds' reviews. That means:
- the card date shows the newest one;
- while round 2 is still unreviewed, round 1's approved review keeps the platform covered.

## API

### `POST /api/projects/{project_id}/cycles` (single initiation, changed)

- `assignments` may cover **any non-empty subset** of the project's platforms, with no duplicates and only the project's own platforms. The error is "Assign a reviewer to at least one of the project's platforms."
- **If the quarter has no cycle:** a cycle is created with those platforms, the same as today.
- **If the quarter already has a cycle:** the request **adds** the missing platforms to it, which is how "Initiate iOS" works.
  - Asking for a platform that's already in the cycle returns 409: "{platform} has already been initiated this quarter."
  - The `can_initiate` check doesn't apply when adding to an existing cycle. Its precondition is only that the quarter has started.
- **Emails:** `cycle_initiated` goes to the PMs, with `platforms: [...]` in the payload, and `reviewer_assigned` goes to each reviewer. The PM message names the platforms started.

### Quarter entry (`GET /api/quarterly`)

- **`can_initiate`:** unchanged. True only when there's no cycle.
- **`uninitiated_platforms`** (new): the project's platforms with no assignment in the cycle. With no cycle, it's every platform.
- **`can_add_platforms`** (new): true when a cycle exists, `uninitiated_platforms` isn't empty, the quarter has started, and the platforms aren't all covered.
- **Each assignment dict gains:**
  - `round`
  - `approved_rounds`: the number of approved rounds, meaning archived rounds with `approved_at`, plus 1 if the current review is approved
  - `can_reinitiate`: true when `review_status == "approved"`
  - `history`: the archived rounds, `[{round, review_id, reviewer_name, approved_at}]`, oldest first

### `POST /api/cycles/{cycle_id}/assignments/{platform}/reinitiate` (new, `cycles.initiate`)

- **Body:** `{reviewer_id}`. It must be an active reviewer, management or admin account.
- **409** unless the current review is approved: "Only an approved review can be reinitiated."
- **404** for an unknown cycle or platform.
- **What it does:**
  1. Inserts a history row with the current round, review_id, reviewer_id and approved_at, plus `archived_by` and `archived_at`.
  2. Resets the assignment:
     - `round += 1`
     - `reviewer_id` is set to the given reviewer, with `reviewer_assigned_by` and `reviewer_assigned_at` recorded
     - `run_status = "waiting_for_url"`
     - cleared to null: `devops_url`, `devops_branch`, `url_submitted_*`, `run_phase`, `run_progress`, `run_error`, `failure_kind`, `review_id`, `queued_at`, `started_at`, `finished_at`, `cancel_requested`, the overrides, the reminded-at fields, `source_type`, and the `source_zip_*` fields
     - `attempts = 0`
  3. Sends emails:
     - `cycle_reinitiated` to the project's PMs. Subject: "Action needed: add the source for {project} · {platform} (Q{q} {year}) — round {n}".
     - `reviewer_assigned` to the reviewer, with `round` in the payload. The subject appends " — round {n}" when the round is above 1.
- **Returns** the assignment dict.

### Bulk

- **`bulk-preview`:**
  - **Eligibility** also includes projects that have a cycle with `can_add_platforms`.
  - **Only the missing platforms are listed.** A project's `platforms` contains just its `uninitiated_platforms`.
  - **Skip reasons:**
    - "Already initiated" now means every platform has been initiated.
    - The other reasons are unchanged.
- **`bulk-initiate`:**
  - **A project's `assignments`** may be any non-empty subset of its platforms. The single-initiation rules apply, including adding platforms to an existing cycle.
  - **Project with no assignments:** it's skipped with the reason "No platforms selected".
  - **Digests:**
    - The PM digest lists each project together with its platforms, as `projects: [{name, platforms}]`.
    - The reviewer digest is unchanged.

## Frontend

- **`InitiateCycleDialog`** (also used for "Initiate iOS"):
  - **Tick boxes:** each platform has one, and only ticked platforms show and require a reviewer select. Its `platforms` prop is the platforms on offer, which is `uninitiated_platforms` when adding to a cycle.
  - **Submit:** enabled when at least one platform is ticked and every ticked platform has a reviewer.
  - **Title:** "Initiate Q4 2026 review — Alpha" for a new cycle, or "Add platforms — Alpha · Q4 2026" when adding.
- **`QuarterCard`:**
  - **Uninitiated platforms:** when there's a cycle, a platform without an assignment shows "· Not started".
  - **Initiate remaining:** with `can_add_platforms` and the permission, the card gets an **Initiate remaining** action that opens the dialog in add mode.
  - **Review count:** a platform with `approved_rounds > 1` shows "· {n} reviews".
- **`ManageCycleDialog`:**
  - **Reinitiate:** an action on rows with `can_reinitiate`. It opens a small inline form with a reviewer select, pre-filled with the current reviewer, and a confirm button.
  - **Round labels:** rows show "Round {n}" when `round > 1`.
  - **Earlier rounds:** a toggle lists the history, with links to `/review/{review_id}` and approved dates.
  - **Uninitiated platforms:** they're listed as "Not started" with an **Initiate** button, which opens the add dialog.
- **`BulkInitiateDialog`:**
  - **Empty slots are allowed.** The submit button counts the projects that have at least one filled slot, and is disabled when there are none.
  - **Only filled slots are posted.**
  - **Empty slot hint:** a ticked project with some empty slots shows "{platform} left for later".
- **`QueuePage`:** the Stop button gets an inline ■ (square) icon before the text and uses the `btn-danger` style. The other actions are unchanged.

## Testing

**Backend:**
- **Partial create:** a subset is created; adding platforms to an existing cycle works; a duplicate or foreign platform is rejected; adding is refused before the quarter starts; the emails list the platforms.
- **Quarter entry:** `uninitiated_platforms` and `can_add_platforms` are correct.
- **Reinitiate:**
  - 409 unless approved;
  - the history row is written;
  - every reset field is cleared;
  - the round is incremented and the reviewer is validated;
  - the emails go out, and `approved_rounds` and `history` are correct;
  - coverage still counts round 1's review for the quarter, and the newest review wins;
  - permissions.
- **Bulk:** partial projects are eligible; an empty assignments list gives "No platforms selected"; the digests carry platforms.
- **Project deletion** removes the rounds.

**Frontend:**
- the initiate dialog's tick boxes and add mode;
- the card's "Not started", "Initiate remaining" and review count;
- the Manage reinitiate form, the history and the per-platform Initiate;
- the bulk dialog's partial submit body and hint;
- the queue Stop icon.

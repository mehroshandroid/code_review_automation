# Automated Cycle Reviews (Part 2, slice 2) — Design Spec

**Date:** 2026-10-07
**Status:** Approved in brainstorming
**Branch:** `automated-reviews`, stacked on `quarterly-cycles`

## Context

Slice 1 (`2026-10-07-quarterly-dashboard-design.md`) lets a coordinator start a quarter's review cycle for a project and assign a reviewer to each platform. Nothing happens after that yet. This slice adds:

- the PM entering an Azure DevOps repo URL for each platform;
- an org-wide DevOps PAT;
- a queue that runs those reviews automatically with the org defaults;
- failure handling and retries;
- coordinators changing reviewers at any time;
- a **notification outbox** that records every workflow email for Part 3's mailer to send.

The coordinator stage tracker and reminder buttons are the next slice (3), built together with Part 3 emails.

## Goals

- **PMs** see the started cycles for their projects at the top of their dashboard. For each platform they enter a DevOps URL (and an optional branch), see its run status, and can retry after a failure.
- **Automatic runs:** saving a URL queues an automatic review. One worker runs the queue oldest-first, so only one review runs at a time.
- **Restarts:** the queue and progress are stored in the database. A backend restart puts interrupted runs back in the queue, along with runs that failed for system reasons.
- **Failures:** a failure shows its error to the PM, and records a notification for all admins.
- **After success:** the URL is locked once a run succeeds. A coordinator or admin can re-run it with a new URL until the review is approved.
- **Changing reviewers:** coordinators, Management and admins can change a platform's reviewer at any stage until that review is approved. Both the new and the previous reviewer are notified.
- **Settings:** an encrypted org DevOps PAT (only admins can change it, and it's never returned to the browser), and a compile-check mode for each platform for automatic runs.
- **Outbox:** every workflow email from now on is recorded in `notification_outbox`.

## Non-goals

- Sending email (Part 3), the stage tracker and reminders (slice 3).
- Running more than one review at a time, and running the worker on more than one backend instance.
- Editing a cycle's platform list after it has started.

## Data model (one Alembic migration, down_revision `c3d4e5f6a7b8`)

**`review_cycle_assignments` gains:**

| Column | Notes |
|---|---|
| `devops_url` | String, nullable |
| `devops_branch` | String, nullable |
| `url_submitted_by` | → users, SET NULL |
| `url_submitted_at` | DateTime(tz) |
| `run_status` | String, not null, server default `'waiting_for_url'`. One of `waiting_for_url`, `queued`, `running`, `completed`, `failed` |
| `run_phase` | String, nullable. The pipeline's phase, copied while it runs |
| `run_progress` | Integer, nullable. 0–100 |
| `run_error` | String, nullable |
| `failure_kind` | String, nullable. `url` or `system` |
| `review_id` | → platform_reviews, SET NULL. The latest run |
| `attempts` | Integer, not null, default 0 |
| `queued_at`, `started_at`, `finished_at` | DateTime(tz) |
| `reviewer_assigned_by` | → users, SET NULL |
| `reviewer_assigned_at` | DateTime(tz) |

**`org_settings` gains:**

| Column | Notes |
|---|---|
| `devops_pat_encrypted` | Text, nullable |
| `devops_pat_last4` | String, nullable |
| `devops_pat_updated_at` | DateTime(tz) |
| `devops_pat_updated_by` | → users, SET NULL |
| `auto_compile_modes` | JSON, nullable |

When `auto_compile_modes` is null the effective default is `{"Android": "compiler", ".NET": "compiler", "iOS": "static"}`.

**New `notification_outbox` table:**

| Column | Notes |
|---|---|
| `id` | String, primary key |
| `event` | String |
| `recipient_user_id` | → users, CASCADE |
| `payload` | JSON |
| `created_at` | DateTime(tz) |
| `sent_at` | DateTime(tz), nullable |

## Secrets

- **Encryption:** `app/secrets.py` encrypts with Fernet (`cryptography`, added explicitly to requirements). The key comes from env `SETTINGS_ENCRYPTION_KEY`, which should be a Fernet key. If that isn't set, it is derived from `AUTH_SECRET_KEY` using SHA-256 and url-safe base64.
- **Never returned:** the plaintext PAT is never returned by any endpoint and never logged.
- **⚠ Deploy note:** set `SETTINGS_ENCRYPTION_KEY` in production. Changing the key (or `AUTH_SECRET_KEY` when no dedicated key is set) makes the stored PAT unreadable. Automatic runs then fail with a `system` error until an admin re-enters the PAT.

## Capabilities

| Capability | Roles | Notes |
|---|---|---|
| `cycles.submit_urls` | admin, management, coordinator, project_manager | PMs are limited to their visible projects |
| `settings.devops_pat` | admin | |

Existing capabilities that cover this slice:
- `cycles.initiate` covers re-running.
- `reviews.assign_reviewer` covers changing reviewers.
- `settings.manage` covers the compile modes.

## Run lifecycle

`waiting_for_url` → (URL saved) → `queued` → (worker) → `running` → `completed` | `failed`

- **Saving or retrying:** saving a URL, or pressing retry, is allowed when the status is `waiting_for_url` or `failed`. It sets `queued` and `queued_at`, and clears the error.
- **Re-running:** allowed when the status is `completed` and the latest review isn't `approved`. It is done by a coordinator or admin (`cycles.initiate`) with a new URL and sets `queued`. The earlier review stays in the history.
- **Worker (`app/automation/worker.py`):** started from the FastAPI lifespan **only when `REVIEW_WORKER_ENABLED=true`**. That variable is set in docker-compose and never set in tests.
  - **On start:**
    - assignments left in `running` go back to `queued`;
    - `failed` assignments with `failure_kind='system'` go back to `queued`.
  - **Loop:** every 5 seconds it claims the oldest `queued` assignment and runs it.
- **Running one assignment:**
  1. Set `running`, `started_at` and `attempts += 1`.
  2. Read the org PAT. If none is configured or it can't be decrypted, the run fails as `system` with "No usable Azure DevOps PAT is configured in Settings."
  3. Resolve the inputs:
     - template: the platform's sample template; a missing one means a `system` failure;
     - LLM: the org default provider and model;
     - compile mode: the platform's entry in `auto_compile_modes`.
  4. Run the existing `_run_review` pipeline in the same process, using the PAT and URL. While it runs, a side task copies `phase` and `progress` to the assignment every 3 seconds.
  5. The pipeline saves the review itself, as it does today, with `project_id` set and `project_name` = project name.
  6. **On success:** set the review's `reviewer_id` to the assigned reviewer, and the assignment's `completed`, `review_id`, `finished_at` and `run_progress` 100. Notify the reviewer.
  7. **On error:** set `failed`, `run_error`, `failure_kind`, `review_id` (the errored review) and `finished_at`. Notify every active admin.
- **Implementation note:** the review row is created by the pipeline when it finishes, not when it starts. The progress of a run in flight is held on the assignment row instead, so it still survives a restart.

**Failure kinds.** The pipeline sets `state["error_kind"] = "url"` for:
- a DevOps fetch with status `invalid_url` or `not_found`;
- an analyzer `fatal_error`, for example the repo isn't a project of that platform.

Everything else is `system`:
- PAT unauthorized (401/403), because the org PAT is the admin's to fix;
- compiler, Mac agent or LLM unreachable, timeouts, unexpected errors;
- a missing PAT or template.

`url` failures need the PM to fix the URL. `system` failures need an admin, and are re-queued automatically on restart and whenever an admin saves the PAT.

## Notifications (outbox events)

| Event | Recipients | When |
|---|---|---|
| `cycle_initiated` | the project's PMs | A cycle is started |
| `reviewer_assigned` | the reviewer | At initiation, for each platform, and on a reviewer change |
| `reviewer_unassigned` | the previous reviewer | On a reviewer change |
| `review_ready` | the assigned reviewer | An automatic run completes |
| `review_failed` | all active admins | An automatic run fails |
| `review_finalized` | the project's PMs | A cycle-linked review is approved |

- **Payload:** each entry holds the project name, platform, year and quarter, and where relevant the review id, error, `failure_kind`, and a `link` path (for example `/reports/{review_id}`).
- **Recipients:** inactive users are skipped.

## API

**PM cycles:**
- **`GET /api/my/cycles`** (`cycles.submit_urls`) returns the cycles for the caller's visible projects (all projects for staff) that have at least one assignment not `completed`, newest first. Each comes as `{id, project_id, project_name, year, quarter, initiated_at, assignments: [assignment dicts]}`.
- **Assignment dict:**

  ```text
  {platform, reviewer_id, reviewer_name, devops_url, devops_branch, run_status, run_phase,
   run_progress, run_error, failure_kind, review_id, review_status, attempts,
   queued_at, started_at, finished_at, queue_position}
  ```

  `queue_position` is 1-based for `queued`, otherwise null.

**URL, retry and re-run:**
- **`PUT /api/cycles/{cycle_id}/assignments/{platform}/url`** with body `{devops_url, devops_branch?}` (`cycles.submit_urls`, with PMs limited to their projects):
  - returns 404 for an unknown or invisible cycle or platform;
  - returns 400 if the URL fails `parse_repo_url`;
  - returns 409 unless the status is `waiting_for_url` or `failed`;
  - otherwise sets the status to `queued` and returns the assignment dict.
- **`POST /api/cycles/{cycle_id}/assignments/{platform}/retry`** (`cycles.submit_urls`): only when `failed`, otherwise 409. Sets `queued`.
- **`POST /api/cycles/{cycle_id}/assignments/{platform}/rerun`** with body `{devops_url, devops_branch?}` (`cycles.initiate`): only when `completed` and the review isn't approved, otherwise 409. Sets `queued` with the new URL.

**Changing the reviewer:**
- **`PUT /api/cycles/{cycle_id}/assignments/{platform}/reviewer`** with body `{reviewer_id}` (`reviews.assign_reviewer`):
  - returns 409 if the assignment's review is `approved`;
  - returns 400 for an invalid reviewer (same rule as initiation);
  - otherwise updates the assignment, and the review's `reviewer_id` if a review exists, records `reviewer_assigned_by/at`, sends notifications (none if the reviewer didn't change), and returns the assignment dict.

**Settings (automation):**
- **`GET /api/settings/automation`** (`settings.manage`) returns:

  ```text
  {pat: {configured, last4, updated_at, updated_by_name}, compile_modes: {...effective}}
  ```

- **`PUT /api/settings/devops-pat`** with body `{pat}` (`settings.devops_pat`):
  - returns 400 for an empty PAT;
  - stores it encrypted, along with `last4`, `updated_at` and `updated_by`;
  - re-queues `failed` `system` assignments;
  - returns the `pat` summary.
- **`PUT /api/settings/auto-compile-modes`** with body `{modes}` (`settings.manage`): keys must be tracked platforms. Allowed values are `compiler`, `static` and, for Android, `local`. Returns the effective modes.

**Changes to existing endpoints:**
- `GET /api/quarterly`: each `cycle.assignments[]` item becomes the full assignment dict.
- `POST /api/projects/{id}/cycles`: records outbox entries `cycle_initiated` and `reviewer_assigned`, and leaves assignments in `waiting_for_url`.
- `PATCH /api/reviews/{id}`: when the status changes to `approved` and the review is the `review_id` of a cycle assignment, records `review_finalized` for the project's PMs.

## Frontend

- **PM dashboard (`ProjectDashboardPage`):** when the user has `cycles.submit_urls` and `dashboard.view_assigned`, a **Pending quarterly reviews** panel appears above the filters. It uses `GET /api/my/cycles` and is hidden when that list is empty.
  - **Per cycle:** a card titled "{project} · Q{n} {year} review", started on {date}.
  - **Per platform:** one row with the platform, the reviewer, a status badge and an action.

    | Status | Badge | Action |
    |---|---|---|
    | Waiting for URL | "Waiting for URL" | URL and branch inputs with **Save & queue** |
    | Queued | "Queued · #2" | — |
    | Running | "Running · {phase} {progress}%" | — |
    | Completed | "Completed" | **View** link to `/reports/{review_id}` |
    | Failed | "Failed" | The error text and the editable URL, with **Save & retry** |

  - **Auto-refresh:** every 10 seconds while any assignment is `queued` or `running`.
- **Quarter card (coordinator):** when `entry.cycle` exists and the user has `cycles.initiate`, a **Manage** button opens `ManageCycleDialog`.
  - **One row per platform:**
    - the URL, read-only, with a status badge (the same labels as the PM panel);
    - a **Reviewer** select, disabled once the review is approved, that saves on change;
    - **Retry** when `failed`;
    - **Re-run** when `completed` and not approved, which asks for a new URL inline.
  - **Effect:** changes update the card in place. The card's platform lines also show "Running"/"Failed"/"Queued" when relevant.
- **Settings page:** a new **Automatic reviews** section.
  - **DevOps PAT:** shows "Configured · ••••{last4} · updated {date} by {name}" or "Not configured". A password input and **Save PAT** are shown only to holders of `settings.devops_pat`.
  - **Compile check for automatic reviews:** one select per platform (Android: Docker lint / Local lint / Static; .NET: Docker build / Static; iOS: Mac build agent / Static) with **Save**.

## Deploy notes (needs attention)

1. Set `SETTINGS_ENCRYPTION_KEY` (generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) before an admin saves the PAT.
2. The PAT needs at least **Code (Read)** on every project's repos.
3. `REVIEW_WORKER_ENABLED=true` must be set on exactly one backend instance. docker-compose sets it.

## Testing

**Backend:**
- **Encryption:** round-trip, the key fallback, and that a wrong key gives a clean `None` rather than a crash.
- **Migration defaults:** existing assignments end up as `waiting_for_url`.
- **Endpoints:** each new one, with permissions; PMs limited to their projects; each 409/400 rule.
- **Initiation:** records the outbox entries.
- **Reviewer change:**
  - updates the review's reviewer and notifies the old and new reviewers;
  - is blocked once approved.
- **Approval:** records `review_finalized`.
- **Worker, with `_run_review` faked:**
  - claims the oldest queued assignment;
  - success links the review, sets its reviewer and notifies the reviewer;
  - a `url` failure is recorded and notifies admins;
  - a missing PAT is a `system` failure;
  - recovery re-queues `running` and `system`-failed assignments but not `url`-failed ones;
  - saving the PAT re-queues `system` failures;
  - progress is synced.
- **Pipeline:** sets `error_kind` for fetch `invalid_url`/`not_found` and for analyzer fatal errors, and not for `unauthorized`.

**Frontend:**
- **Pending panel:** every status's row and action; Save & queue calls the API; Save & retry; the auto-refresh timer.
- **ManageCycleDialog:** reviewer change, Retry, Re-run, and the select disabled once approved.
- **Settings:** the PAT summary, PAT save (admin only), and saving compile modes.
- **Quarter card:** the Manage button and the run status lines.

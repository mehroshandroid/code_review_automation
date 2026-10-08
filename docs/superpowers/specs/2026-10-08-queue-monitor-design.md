# Admin Queue Monitor — Design Spec

**Date:** 2026-10-08
**Status:** Approved in brainstorming
**Branch:** `queue-monitor`, stacked on `automated-reviews`

## Context

Automated cycle reviews (`2026-10-07-automated-cycle-reviews-design.md`) run one at a time from a database-backed queue. Today admins can't see or steer that queue. This adds a live **Queue** page where admins can:
- see what is running, queued, failed and recently completed;
- pause and resume the queue;
- act on individual items: stop, remove, move to front, retry, and per-run settings.

## Decisions

- **A new tab, "Queue", placed right after "Users".** It's admin only, behind a new capability `queue.manage` (admin).
- **The Settings page is unchanged.** The PAT and the compile checks for automatic runs stay where they are, and they remain the defaults. Nothing about the queue is stored in `org_settings`.
- **Pause state** lives in a new singleton table, `review_queue_state`.
- **Pause stops the running review immediately.** It goes back to the **front** of the queue with no error and no notification, nothing is saved for the cancelled run, and it restarts from scratch on resume.
- **Per-run settings, as a row action:** an LLM provider (and model) and a compile check override for **that one review**. A blank field uses the org default. Overrides can be edited while the item is `waiting_for_url`, `queued` or `failed`; a `running` or `completed` item can't be changed. Overrides stay on the row, so retries and re-runs keep them until cleared.
- **Item actions:**

  | Action | Allowed when | Effect |
  |---|---|---|
  | **Stop** | `running` | `failed` with `failure_kind="stopped"` and "Stopped by an admin.". Not re-queued automatically |
  | **Remove** | `queued` | Back to `waiting_for_url` with the URL kept. The project's PMs are notified (`review_removed_from_queue`) |
  | **Move to front** | `queued` | The item becomes the next to run |
  | **Retry** | `failed` | Uses the existing retry endpoint |

- **The page refreshes every 5 seconds.**

## Data model (one migration, down_revision `e5f6a7b8c9d0`)

- **New table `review_queue_state`:**

  | Column | Type |
  |---|---|
  | `id` | Integer, primary key; always 1 |
  | `paused` | Boolean, not null, default false |
  | `paused_by` | → users, SET NULL |
  | `paused_at` | DateTime(tz) |

- **`review_cycle_assignments` gains:**

  | Column | Notes |
  |---|---|
  | `cancel_requested` | String, nullable. `pause` or `stop` |
  | `override_llm_provider` | String, nullable |
  | `override_llm_model` | String, nullable |
  | `override_compile_mode` | String, nullable |

- **`failure_kind`** gains a third value, `stopped`. It is never re-queued by `recover()` or by saving the PAT; those only re-queue `system` failures.

## Worker changes

- **`run_one()`** returns `False` without claiming anything while the queue is paused, so the loop idles.
- **The pipeline runs as its own task.** The progress sync, every `PROGRESS_SYNC_SECONDS`, re-reads the row. If `cancel_requested` is set, it sets `state["cancelled"] = <value>` and cancels the pipeline task.
  - **`_run_review` skips persisting** when `state["cancelled"]` is set, so a cancelled run leaves no review row.
  - **`pause`:** `queued` at the front, with `cancel_requested`, phase and progress cleared.
  - **`stop`:** `failed`, `failure_kind="stopped"`, `run_error="Stopped by an admin."`, `finished_at` set, and `cancel_requested` cleared.
  - **No notifications** for either.
- **Overrides:**
  - Provider: `override_llm_provider or org.default_llm_provider`.
  - Model: `override_llm_model` when a provider override is set, otherwise `org.default_ollama_model`.
  - Compile mode: `override_compile_mode or effective_compile_modes(org.auto_compile_modes)[platform]`.
- **`recover()`** also clears `cancel_requested` on the rows it re-queues.
- **Shutdown during a run** stays as it is today: the row is re-queued on the next start.

## API (`app/api/queue.py`, all `queue.manage`)

- **`GET /api/queue`** returns:

  ```text
  {paused, paused_by_name, paused_at, running: [item], queued: [item],
   failed: [item] (50 newest by finished_at), completed: [item] (20 newest by finished_at),
   waiting_for_url: <count>, defaults: {llm_provider, llm_model, compile_modes}}
  ```

  - **Item:** the existing assignment dict plus `cycle_id`, `project_id`, `project_name`, `year`, `quarter`, `cancel_requested`, `override_llm_provider`, `override_llm_model` and `override_compile_mode`. Queued items come in run order, with `queue_position`.
- **`POST /api/queue/pause`:** sets paused, records who and when, and sets `cancel_requested='pause'` on running rows. Returns the queue.
- **`POST /api/queue/resume`:** clears paused. Returns the queue.
- **`POST /api/queue/items/{cycle_id}/{platform}/stop`:** running only, otherwise 409. Sets `cancel_requested='stop'`. Returns the item.
- **`POST .../remove`:** queued only, otherwise 409. Sets `waiting_for_url`, clears `queued_at`, notifies PMs. Returns the item.
- **`POST .../front`:** queued only, otherwise 409. Sets `queued_at` to just before the earliest queued item. Returns the item.
- **`PUT .../settings`** with body `{llm_provider, llm_model, compile_mode}`, each nullable:
  - returns 409 for `running` or `completed`;
  - returns 400 for an unknown provider (`azure|ollama|claude`) or a compile mode not allowed for the platform;
  - when the provider is null, the model is cleared;
  - returns the item.
- **404** for an unknown cycle or platform.
- **Retry:** uses the existing `POST /api/cycles/{id}/assignments/{platform}/retry`. Admins already hold `cycles.submit_urls`.

## Frontend

- **`AppNav`:** a "Queue" link (`/queue`) after "Users", shown for `queue.manage`.
- **Route:** `/queue`, guarded by `queue.manage`.
- **`QueuePage`:**
  - **Header:** "Review queue", a status pill (**Running**, **Idle**, or **Paused by X · time**), Pause/Resume, and "Updated Ns ago". It polls `GET /api/queue` every 5 seconds.
  - **Pause confirmation dialog:** "The running review will be stopped and restarted from the beginning when you resume."
  - **Defaults line:** "Defaults: {provider} · Android {mode}, .NET {mode}, iOS {mode} (change in Settings)".
  - **Panels, each with an empty state:**

    | Panel | Shows | Actions |
    |---|---|---|
    | **Running now** | Project · platform · Qn year, phase, a progress bar with %, elapsed time since `started_at`, attempt number, override chips | **Stop** (confirm). Shows "Stopping…" when `cancel_requested` is set |
    | **Queued** | Position, project · platform · quarter, reviewer, time waited, override chips | **Move to front** (hidden for #1), **Remove** (confirm), **Run settings** |
    | **Failed** | The error, a kind tag (URL / System / Stopped), finished time | **Retry**, **Run settings** |
    | **Recently completed** | Finished time, duration | **View** link to the report |

  - Waiting for URL is shown as a count only.
- **`RunSettingsDialog`:**
  - **LLM provider select:** "Org default ({provider})", Azure OpenAI, Ollama (local), Claude CLI (local).
  - **Ollama model:** a select from `GET /api/ollama/models` when Ollama is chosen, with a text input as a fallback.
  - **Compile check select:** "Org default ({mode})" plus the options allowed for the platform.
  - **Save** and **Clear overrides**.

## Testing

**Backend:**
- **Pause gate:** nothing is claimed while paused.
- **Pause and stop cancel a running fake pipeline:**
  - a pause re-queues at the front and stores no review;
  - a stop fails with `stopped` and stores no review;
  - `recover()` doesn't re-queue `stopped`.
- **Overrides** reach the pipeline call, with the fallbacks.
- **Queue endpoints:**
  - the response shape and ordering;
  - each action's allowed and forbidden states (409), and 404;
  - a remove notifies the PMs;
  - the settings validation;
  - admins only (403 for Management and coordinators).

**Frontend:**
- **QueuePage:** panels and empty states, the polling interval, pause confirm and resume, the item actions call the API, and "Stopping…".
- **RunSettingsDialog:** the defaults labels, the Ollama model field, save, and clear.
- **AppNav:** the Queue link for admins only, placed after Users.

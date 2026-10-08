# Email Delivery, Stage Tracker & Reminders (Part 2 slice 3 + Part 3) — Design Spec

**Date:** 2026-10-08
**Status:** Approved in brainstorming
**Branch:** `email-and-tracker`, from `master` (`0dd070f`)

## Context

Since the automated-reviews slice, every workflow email has been recorded in `notification_outbox`, but nothing sends them. Coordinators also can't see where each platform's review stands or nudge the people involved. This slice adds:

1. **A mailer** that delivers the outbox, through Microsoft Graph or SMTP, configured by environment. It defaults to a log-only mode until the org mailbox exists.
2. **A per-platform stage tracker:** dots on quarter cards, with full detail in the Manage dialog.
3. **Manual reminders** to the PM and to the reviewer.
4. **An admin Email section** in Settings: status, test email, recent emails, and retry.

## Decisions

- **Configuration lives in environment variables, not the database.** Secrets stay in deployment configuration.
- **Delivery modes:** `log` (default), `graph`, `smtp`.
- **Graph** falls back to the existing `AZURE_AD_*` sign-in app credentials when `GRAPH_*` aren't set.
- **Reminders are manual only.** They're available to anyone with `cycles.initiate` (coordinator, Management, admin).
- **Existing outbox rows are marked `skipped`** by the migration, so nobody receives stale emails when real delivery is turned on.
- **The email section is admin only**, through a new capability `email.manage`.

## Configuration (environment)

| Variable | Meaning |
|---|---|
| `EMAIL_MODE` | `log` (default) \| `graph` \| `smtp` |
| `EMAIL_FROM` | Sender address, e.g. `codeassure@teo-intl.com` |
| `EMAIL_FROM_NAME` | Default `CodeAssure` |
| `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` | Fall back to `AZURE_AD_TENANT_ID` / `AZURE_AD_CLIENT_ID` / `AZURE_AD_CLIENT_SECRET` |
| `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS` (true) | SMTP settings |
| `FRONTEND_BASE_URL` | Already exists. The base for links in emails |

**When a mode counts as "configured":**
- `log`: always.
- `graph`: `EMAIL_FROM` and all three Graph values are set.
- `smtp`: `EMAIL_FROM`, `SMTP_HOST` and `SMTP_PORT` are set.

**An unconfigured `graph` or `smtp` mode** leaves emails `pending`, and they are retried until they fail.

## Data model (migration `a7b8c9d0e1f2`, down_revision `f6a7b8c9d0e1`)

**`notification_outbox` gains:**

| Column | Notes |
|---|---|
| `status` | String, not null, server default `'pending'`. One of `pending`, `sent`, `failed`, `logged`, `skipped` |
| `attempts` | Integer, not null, default 0 |
| `last_error` | Text, nullable |
| `next_attempt_at` | DateTime(tz), nullable |
| `subject` | String, nullable. Filled when the email is rendered |

**The migration also runs `UPDATE notification_outbox SET status='skipped'`** for every existing row.

**`review_cycle_assignments` gains:** `pm_reminded_at` and `reviewer_reminded_at`, both DateTime(tz) and nullable.

## Mailer

- **`app/email/config.py`:**
  - `email_settings()` reads the environment.
  - `describe()` returns a safe summary: `{mode, from_address, from_name, base_url, configured, problems: [str]}`. It never includes a secret.
- **`app/email/templates.py`:** `render(event, payload, recipient) -> (subject, html, text)`. Every payload value is HTML-escaped, and links are `base_url + payload["link"]`.

  | Event | Subject |
  |---|---|
  | `cycle_initiated` | "Action needed: add DevOps URLs for {project} · Q{q} {year} review" |
  | `reviewer_assigned` | "You're the reviewer for {project} · {platform} (Q{q} {year})" |
  | `reviewer_unassigned` | "You're no longer reviewing {project} · {platform} (Q{q} {year})" |
  | `review_ready` | "Ready for your review: {project} · {platform} (Q{q} {year})" |
  | `review_failed` | "Automatic review failed: {project} · {platform} (Q{q} {year})" |
  | `review_finalized` | "Review finalized: {project} · {platform} (Q{q} {year}) — {score}%" (without the score part when there is no score) |
  | `review_removed_from_queue` | "Please check the DevOps URL for {project} · {platform} (Q{q} {year})" |
  | `reminder_pm` | "Reminder: add the DevOps URL for {project} · {platform} (Q{q} {year})" |
  | `reminder_reviewer` | "Reminder: {project} · {platform} (Q{q} {year}) is waiting for your review" |
  | `test_email` | "CodeAssure test email" |

  An unknown event renders a generic "CodeAssure notification".
- **`app/email/transport.py`:** `async send(settings, to_address, to_name, subject, html, text)`.
  - **`log`:** logs the subject and recipient at INFO.
  - **`smtp`:** `smtplib` run in `asyncio.to_thread`, using STARTTLS and login when a username is set, with a multipart/alternative message.
  - **`graph`:** gets an app-only token through `msal.ConfidentialClientApplication(...).acquire_token_for_client(["https://graph.microsoft.com/.default"])`, then calls `POST https://graph.microsoft.com/v1.0/users/{from}/sendMail` with an HTML body (`saveToSentItems: false`).
  - **Failures** raise `EmailError(message)`, and the message must not contain secrets.
- **`app/email/sender.py`:**
  - **`deliver_due(limit=20) -> int`:** picks rows where `status='pending'` and (`next_attempt_at` is null or due), oldest first.
    - If the recipient is missing or inactive, the row becomes `skipped`.
    - Otherwise it renders the email, stores the `subject`, and sends.
    - **On success:** `sent`, or `logged` in log mode, and `sent_at` is set.
    - **On failure:** `attempts += 1`, and `last_error` is set. After 5 attempts the row becomes `failed`; before that, `next_attempt_at` is set to `now + 2^attempts minutes`.
  - **`email_loop()`:** waits on an `asyncio.Event`, with a 15-second timeout, then calls `deliver_due`.
  - **`wake()`:** sets the event. It is a no-op when the loop isn't running.
  - **`start_email_worker()`:** starts the loop. It is started in the lifespan together with the review worker (`REVIEW_WORKER_ENABLED=true`).
- **`notify()`** (in `app/automation/notify.py`) calls `wake()` after inserting rows, so manual reminders and test emails go out within seconds.

## Stage tracker data

The assignment dict gains these fields:
- `url_submitted_at`
- `review_approved_at`, from the linked review's `approved_at`
- `pm_reminded_at`, `reviewer_reminded_at`

`initiated_at` is already on the cycle.

| Stage | Done when | Timestamp |
|---|---|---|
| Initiated | Always, once a cycle exists | `cycle.initiated_at` |
| URL added | `url_submitted_at` is set | `url_submitted_at` |
| AI review done | `run_status == 'completed'`; **failed** when `run_status == 'failed'` | `finished_at` |
| Reviewer feedback | `review_status == 'approved'` | `review_approved_at` |

## Reminders

**`POST /api/cycles/{cycle_id}/assignments/{platform}/remind`** with body `{target: "pm" | "reviewer"}` (`cycles.initiate`):

| Target | Allowed when | Effect |
|---|---|---|
| `pm` | `run_status == 'waiting_for_url'`, or `failed` with `failure_kind == 'url'` | `reminder_pm` to the project's PMs; sets `pm_reminded_at` |
| `reviewer` | `run_status == 'completed'`, the review isn't approved, and a reviewer is assigned | `reminder_reviewer` to the reviewer; sets `reviewer_reminded_at` |

- **Otherwise it returns 409:** "A reminder isn't needed at this stage."
- **404** for an unknown cycle or platform.
- **Returns** the assignment dict.

## Email admin API (`app/api/email_admin.py`, `email.manage`)

- **`GET /api/email/status`** returns `describe()`.
- **`POST /api/email/test`** records a `test_email` to the current user, calls `wake()`, and returns the row.
- **`GET /api/email/outbox?limit=50`** returns the newest rows: `{id, event, recipient_email, recipient_name, subject, status, attempts, last_error, created_at, sent_at}`.
- **`POST /api/email/outbox/{id}/retry`** works only on `failed` rows (409 otherwise). It sets `pending`, `attempts=0`, clears `next_attempt_at` and `last_error`, calls `wake()`, and returns the row.

## Frontend

- **`StageTracker.jsx`:**
  - `stagesFor(assignment, initiatedAt)` returns 4 `{key, label, state: done|pending|failed, at}`.
  - `StageDots` shows 4 small dots, each with a `title` such as "URL added — done 8 Oct, 10:42" or "AI review done — pending" and an `aria-label`.
  - `StageTimeline` shows the labelled stages with timestamps.
- **QuarterCard:** for an initiated cycle, each platform line shows `StageDots`.
- **ManageCycleDialog:**
  - A new "Progress" column with `StageTimeline`.
  - Actions gain **Remind PM** and **Remind reviewer**, shown only when they're allowed.
  - A note "Reminded {relative} ago" from the reminded-at fields.
- **Settings → Email** (`EmailSettingsSection`, `email.manage` only):
  - **Status:** mode, sender, base URL, and "Configured" or the list of problems.
  - A **Send test email** button.
  - A **Recent emails** table (padded): event, recipient, subject, a status badge, attempts and error, with **Retry** on failed rows.
  - A **Refresh** button.

## Deploy notes

- **Until the network team responds:** keep `EMAIL_MODE=log`. Emails show as "logged" in Settings.
- **For Graph:** set `EMAIL_MODE=graph` and `EMAIL_FROM`, plus `GRAPH_*` (or rely on the `AZURE_AD_*` fallback if Mail.Send was granted to the sign-in app).
- **For SMTP:** set `EMAIL_MODE=smtp`, `EMAIL_FROM` and `SMTP_*`.
- **In production:** set `FRONTEND_BASE_URL` to the production address.

## Testing

**Backend:**
- **Config:** the defaults, the Graph fallback, the "configured" rules, and that `describe()` contains no secrets.
- **Templates:**
  - each event has the expected subject;
  - payload values are escaped;
  - the link uses the base URL;
  - a missing score is handled;
  - unknown events render the generic notification.
- **Sender:**
  - log mode marks rows `logged`;
  - a success marks `sent`;
  - failures back off, and the 5th failure becomes `failed`;
  - inactive recipients become `skipped`;
  - only due rows are picked;
  - `wake()` triggers delivery.
- **Transports:** SMTP builds and sends a multipart message (a fake `smtplib.SMTP`); Graph posts the expected JSON with a bearer token (fake msal and httpx); errors raise `EmailError` without secrets.
- **Migration:** existing rows are skipped (checked by running the SQL on SQLite).
- **Remind endpoint:** each allowed and 409 case, the recipients, the timestamps, and permissions.
- **Email admin API:** status, test, outbox listing, retry rules, and admin only.
- **Assignment dict:** carries the new fields.

**Frontend:**
- **`stagesFor`:** every combination.
- **`StageDots`:** titles.
- **ManageCycleDialog:** the Remind buttons' visibility and calls, and the reminded note.
- **QuarterCard:** dots shown only for initiated cycles.
- **EmailSettingsSection:** status/problems, the test button, the table, retry, and hidden for non-admins.

# Frontend + Docker Compose — Design Spec

**Status:** Approved
**Date:** 2026-07-23
**Source:** Companion to `2026-07-23-android-code-review-automation-design.md` (backend). Written against the backend's actual implemented API (verified from `backend/app/api/reviews.py` post-merge), not the original handover doc's response-shape sketch — the backend evolved several fields during implementation.

## Purpose

A single-page React UI: upload an Android ZIP + Excel template, watch live progress, see mid-flight analysis findings (warnings, secrets, coverage), download the populated Excel on completion. Packaged with the backend via Docker Compose.

## Actual Backend API Contract (source of truth for this frontend)

```
POST   /api/reviews
  multipart/form-data: androidZip (file), excelTemplate (file)
  → 200 { review_id: string, status: "processing" | "error" }
  (status "error" here only for upload-save failures, e.g. disk full — rare)

GET    /api/reviews/{review_id}/progress
  → 200 {
      status: "processing" | "completed" | "error",
      phase: "pending" | "extracting" | "analyzing" | "scoring" | "generating" | "completed" | "error",
      progress: number (0-100),
      message: string,
      stats: { ingest_time_ms?, analysis_time_ms?, scoring_time_ms?, generation_time_ms?, total_time_ms? },
      download_url: string | null,   // set once status === "completed"
      error: string | null,
      warnings: string[],            // populated after "analyzing" phase completes
      test_coverage: number | null,  // percentage, populated after "analyzing"
      secrets_found: { file: string, line: number, pattern: string }[],  // populated after "analyzing"
    }

GET    /api/reviews/{review_id}/download
  → 200 binary xlsx (Content-Disposition attachment), deletes server-side temp dir after serving
  → 404 if not ready / already downloaded
```

Key implementation detail: `warnings`/`test_coverage`/`secrets_found` become available partway through processing (after the "analyzing" phase, before "scoring" finishes) — not only at the end. The `FindingsPanel` should render as soon as these are non-empty/non-null, even while `status` is still `"processing"`.

## Stack

- React 18, bootstrapped with Create React App (plain JS, `.jsx` files, no TypeScript).
- Tailwind CSS for styling.
- Axios for HTTP.
- No routing library, no external state manager — this is a single page; `useState`/`useEffect` in `App.jsx` is sufficient.

## Component Structure

```
frontend/src/
  App.jsx                      — owns the state machine (idle/uploading/polling/completed/error), renders children
  components/
    UploadForm.jsx              — two file inputs + submit; client-side extension validation before POST
    ProgressTracker.jsx         — polls progress every 2s while status === "processing"; shows phase + progress bar
    FindingsPanel.jsx           — shows warnings / test_coverage / secrets_found once available (can render mid-poll)
    StatsDisplay.jsx            — shown on completion: timing breakdown + Download button
  services/
    api.js                      — createReview(), getProgress(id), downloadReview(id) — Axios wrappers, base URL from REACT_APP_API_URL
```

## State Machine (App.jsx)

```
idle → (submit) → uploading → (POST resolves) → polling
polling → (poll returns status: "completed") → completed
polling → (poll returns status: "error") → error
uploading → (POST fails, network error) → error
completed | error → (user clicks "Start New Review") → idle
```

`FindingsPanel` renders whenever `warnings`/`test_coverage`/`secrets_found` are present in the latest poll response, regardless of whether the overall state is `polling` or `completed` — it's driven by the poll response fields, not the top-level state machine state.

## Client-Side Validation

`UploadForm` checks file extensions (`.zip` for the Android project, `.xlsx` for the template) before calling the API, giving immediate feedback rather than waiting on a round-trip. This mirrors (does not replace) the backend's own validation in `_run_review`.

## Polling

`setInterval` at 2000ms while `status === "processing"`, cleared on unmount and on reaching `"completed"`/`"error"`. Matches the backend design's documented 2s interval (no WebSocket).

## Error Display

If `status === "error"`, show `error` (the message string) prominently with a "Try Again" button that resets to `idle`. No silent failures — this matches the backend's "always HTTP 200, errors carried in the body" contract, so the frontend must actively check `status`/`error` rather than relying on HTTP status codes for failure detection.

## Docker

- `frontend/Dockerfile`: multi-step but not multi-stage-with-nginx — build the CRA static bundle, then serve it with the `serve` npm package (`npx serve -s build -l 3000`). Simpler than an nginx stage for a POC; no nginx config to maintain.
- `docker-compose.yml`: `backend` service (build `./backend`, port 8000, env vars for Azure OpenAI) + `frontend` service (build `./frontend`, port 3000, `REACT_APP_API_URL=http://localhost:8000/api`, `depends_on: backend`). Matches the original handover doc's compose shape.

## Testing

- Component-level: React Testing Library for `UploadForm` (validation logic), `ProgressTracker` (polling start/stop behavior via mocked timers), `FindingsPanel` (conditional rendering).
- No E2E test against the real backend in this pass — the backend's own integration test (Task 12) already proves the API contract end-to-end; the frontend's tests verify it consumes that contract correctly via mocked API responses.

## Out of Scope (unchanged from backend spec)

- Authentication, multi-user support, persistence beyond the single in-memory `_reviews` dict — this remains a POC.

# Frontend Industry Redesign — Design Spec

**Status:** Approved
**Date:** 2026-07-27
**Source:** Design handoff in `/Users/mehroshmehboob/Downloads/designs/` (`README.md`, `Frontend.dc.html`, `styles.css`) — a high-fidelity prototype built on the "Industry" design system (blueprint/wireframe aesthetic). This spec adapts that prototype to the *existing* real frontend (`frontend/src/App.jsx` and friends), which already talks to the real backend — it does not replace the app's actual state machine or polling logic, only its visuals and a couple of small data gaps.

## Purpose

Restyle the existing single-page upload → progress → findings → download flow to match the Industry design system pixel-for-pixel (per the handoff's "high-fidelity, final" fidelity note), while keeping all real backend interaction (`services/api.js`, polling, error handling) intact.

## Backend Change: `total_score_pct`

The design's completed screen shows a `Total {score}%` tag. No such aggregate currently exists in the API — `GET /api/reviews/{review_id}/progress` returns per-run `stats` (timings only); the per-category `percent_points` values computed in `aggregate_category_scores` (`backend/app/analyzer/excel_handler.py`) are only ever written into the output Excel workbook, never surfaced.

Add to `backend/app/api/reviews.py`:
- After all categories are scored in `_run_review`, compute `total_score_pct = round(mean(percent_points for each category where percent_points is not None), 1)`. If no category has a valid score, `total_score_pct` is `null`.
- Store it on the review state and include it in the `get_progress` response as `total_score_pct: number | null`.

This is the only backend change in scope.

## Updated API Contract

```
GET /api/reviews/{review_id}/progress
  → 200 {
      status, phase, progress, message, stats, download_url, error,
      warnings, test_coverage, secrets_found,
      total_score_pct: number | null   // NEW — mean of category percent_points
    }
```

All other endpoints and fields unchanged from `2026-07-23-frontend-docker-design.md`.

## Frontend Architecture

```
frontend/src/
  design-system.css       — vendored Industry tokens + component classes,
                             adapted from the handoff's styles.css: color
                             ramps, spacing scale, fonts (Barlow / Barlow
                             Condensed), .card/.blueprint/.corner/.btn/.tag/
                             .table/.nav/.input/.field. Imported once in
                             index.js alongside the existing Tailwind
                             index.css. Tailwind remains for minor layout
                             (max-width wrappers, gaps) only — no new
                             tailwind.config tokens.
  icons.jsx               — FileIcon, CheckCircleIcon, SpinnerIcon,
                             CircleIcon, DownloadIcon, ArrowRightIcon: small
                             function components wrapping the exact inline
                             SVG markup from the prototype (stroke-width
                             1.5). No new npm dependency.
  App.jsx                 — same state machine (idle/uploading/polling/
                             completed/error) and same handlers
                             (handleUpload/handleProgressUpdate/handleReset).
                             Now also renders the nav bar (".nav" +
                             ".nav-brand") and the page header (h1 title +
                             description paragraph) once, above whichever
                             phase card is active — matching the prototype's
                             constant page shell.
  components/
    UploadForm.jsx          — restyled as the idle card: kicker "Step 1 of 2",
                              blueprint corners, two-column file fields
                              (FileIcon + filename/placeholder), full-width
                              primary blueprint button ("Start review" +
                              ArrowRightIcon), disabled until both files
                              chosen. Button reads "Starting review…"
                              (disabled) while the create-review request is
                              in flight — no separate uploading screen. No
                              demo-failure button (dropped; not applicable to
                              a real backend).
    ProgressTracker.jsx      — same polling logic (2s interval while
                              status === "processing"). Visually a 4-row
                              step list: "Extracting archive", "Analyzing
                              code", "Scoring with AI", "Generating report".
                              Backend `phase` maps to a step index:
                              pending → -1 (all pending), extracting → 0,
                              analyzing → 1, scoring → 2, generating → 3,
                              completed/error → 4 (all done). Row state is
                              done (i < index), active (i === index),
                              pending (i > index), using CheckCircleIcon /
                              spinning SpinnerIcon / dimmed CircleIcon
                              respectively. The backend's live `message`
                              renders as small muted subtext under the
                              active row only.
    FindingsPanel.jsx        — restyled as the 3-card findings grid
                              (Warnings / Test coverage / Secrets found),
                              shown once any of warnings/test_coverage/
                              secrets_found are present (same trigger as
                              today). Each card shows a big count (or
                              percentage for coverage) and a generic caption
                              ("N issues found" / "No coverage report
                              found." when test_coverage is null / "N
                              possible secrets found"). Warnings and Secrets
                              cards are expandable (click to toggle): expanded
                              state lists every warning as a line, and every
                              secret as `file:line (pattern)`. Test coverage
                              card is not expandable.
    StatsDisplay.jsx         — restyled as the completed card: kicker
                              "Complete", title "Review ready", tag row
                              (`tag-accent` "Total {total_score_pct}%" —
                              omitted if null — plus two `tag-outline` tags
                              for warnings/secrets counts), full-width
                              primary blueprint "Download populated
                              workbook" button (unchanged `getDownloadUrl`
                              wiring), the same findings grid repeated below,
                              a Performance breakdown `.table` (Phase /
                              Duration rows from `stats`, ms values formatted
                              as seconds, e.g. `1.2s`), and a ghost "Start
                              new review" button (unchanged reset behavior).
  services/api.js           — unchanged.
```

## Error Screen

Kicker "Error", title "Review failed", body = `errorMessage` from the backend (unchanged error-detection contract: always HTTP 200, check `status`/`error` in the body). Primary blueprint button "Try again" resets to idle — same `handleReset` as today.

## Testing

- **Backend**: extend `test_reviews_progress.py` and `test_reviews_integration.py` to assert `total_score_pct` is present and correctly computed (mean of category percentages, `null` when no category has a score); add a focused unit test for the new aggregation helper.
- **Frontend**: update existing component tests (`UploadForm.test.jsx`, `ProgressTracker.test.jsx`, `FindingsPanel.test.jsx`, `StatsDisplay.test.jsx`, `api.test.js`) for new markup/class names, the phase→step mapping, and findings-card expand/collapse behavior. No new test infrastructure.

## Out of Scope

- Responsive/mobile breakpoints (per the handoff: "no responsive breakpoints defined... confirm with design before shipping if needed").
- Dark mode.
- Changes to the polling interval, error-detection contract, or Docker/compose setup.
- Auth, multi-user support, persistence beyond the existing in-memory `_reviews` dict.
- The prototype's demo timers/fake data — this is a real UI against the real backend, not a simulation.

# Category Scores Bar Chart — Design Spec

**Status:** Approved
**Date:** 2026-07-28
**Source:** Team demo feedback — "show a bar graph as well on the webpage for each of the heads" (the 5 review categories used in the scoring template).

## Purpose

Today the frontend only ever surfaces a single aggregate `Total {score}%` tag on the completed screen. The backend already computes a per-category percentage (`percent_points`, via `aggregate_category_scores`) while scoring, but never exposes it — only the aggregate mean (`total_score_pct`) is sent to the frontend. This spec adds a per-category bar chart so the team can see the breakdown behind the total, filling in live as each category finishes scoring rather than only appearing once the whole review completes.

## Backend Change: `category_scores`

Add a `category_scores` field to the `/progress` response: a list of `{id, name, percent_points}`, one entry per `CATEGORIES` key, in `CATEGORIES` iteration order.

- Seeded at the **start** of the review (in `_new_review_state()`-adjacent init, once `CATEGORIES` is known) with every category present and `percent_points: null` — so the frontend can render all 5 category rows (as "pending") from the moment the scoring step begins, not just once each arrives.
- Updated **in place** the moment each category's `aggregate_category_scores(...)` call resolves inside the existing scoring loop in `_run_review` (`backend/app/api/reviews.py`) — the same point where `state["progress"]` is already bumped per category. No new LLM calls, no new computation — this only exposes data that already exists in `scores_by_category` at that point in the loop.
- `name` is the human-readable category name already in `CATEGORIES` (e.g. `"Reliability, Security & Observability"`), not the bare id — the frontend needs it directly since it has no other way to map `"2"` to a label.

### Updated API contract

```
GET /api/reviews/{review_id}/progress
  -> 200 {
       ...(all existing fields, unchanged)...
       category_scores: { id: string, name: string, percent_points: number | null }[],
     }
```

## Frontend: `CategoryScoresChart` component

New file `frontend/src/components/CategoryScoresChart.jsx`, built with **Recharts** (new dependency — `recharts`).

- **Form**: horizontal bar chart (Recharts `BarChart` with `layout="vertical"`, i.e. bars grow left-to-right, category names on the Y-axis) — chosen because this is a magnitude comparison across categories whose names are long (e.g. "Reliability, Security & Observability"), which reads far better as horizontal bars than vertical columns per the dataviz form guide.
- **Color**: single hue throughout, `var(--color-accent)` — this is one series (one score per category), not a categorical comparison between distinct series, so no rainbow, no per-bar color variation, and no legend box (the card title "Category scores" already says what's plotted).
- **Mark spec**: bars ~20px thick, 4px rounded end (the value end), square at the baseline (x=0), 2px gap of surface color between adjacent bars.
- **X-axis**: fixed domain 0–100, tick marks at 0/25/50/75/100.
- **Pending categories** (`percent_points: null`): rendered as an empty/dimmed track (no filled bar) with a muted "Pending…" label in place of a value — never a 0%-width bar, which would misread as "scored zero."
- **Scored categories**: filled bar to `percent_points`, with the rounded percentage direct-labeled at the bar's tip (e.g. `"90%"`).
- **Tooltip**: hover/focus on any bar (scored or pending) shows the full category name and either its exact percentage or "Not yet scored." The hovered bar lifts slightly (per dataviz interaction guidance) so hover state is visible.
- **Props**: `CategoryScoresChart({ categoryScores })` — `categoryScores: {id, name, percent_points}[]`, passed straight through from the poll response's new field.

## Placement

- **Running screen** (`App.jsx`, `state === "polling"`): rendered directly below `ProgressTracker`, above `FindingsPanel`, but only once the "Scoring with AI" step has started or later (mirrors the existing `showFindings`-style gating — before scoring starts there's nothing meaningful to show, since every category is still `null`).
- **Completed screen** (`StatsDisplay.jsx`): rendered immediately after the tag row (`Total {score}%` / warnings / secrets tags) and before the nested `FindingsPanel` — headline number first, category breakdown next, supporting detail (findings, timing) after.

## Testing

- **Backend**: extend `test_reviews_create.py` (which already covers `_run_review`'s per-category progress updates) to assert `category_scores` is seeded with all 5 categories at `null` before scoring starts, and that each entry's `percent_points` updates in place as its category's scoring call resolves, without disturbing the others. Extend `test_reviews_progress.py` to assert the field round-trips through the `/progress` response.
- **Frontend**: new `CategoryScoresChart.test.jsx` covering: pending categories render "Pending…" not a bar; scored categories render their labeled percentage; a mixed list (some scored, some pending) renders both states correctly in the same chart. Update `App.test.jsx`/`StatsDisplay.test.jsx` mocks to include `category_scores` in their poll-response fixtures and assert the chart appears in the right place.

## Out of Scope

- No status/threshold coloring (red/amber/green by score) — single accent hue only, consistent with the existing mono-accent design system.
- No dark mode theming for the chart — the app has no dark mode at all today.
- No standalone accessible data table alongside the chart — the direct percentage labels on each bar already carry the values, and the populated Excel workbook remains the authoritative tabular record once the review completes.
- No change to `total_score_pct` or the existing `Total {score}%` tag — this chart is additive detail alongside it, not a replacement.

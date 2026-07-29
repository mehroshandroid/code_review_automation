# Report View, Project Name & Performance Popup — Design Spec

**Status:** Approved
**Date:** 2026-07-29
**Source:** Team demo feedback (round 4) — four related UI requests: show the uploaded project's name, show the actual scored report in-browser (not download-only), let the user switch between the report and the existing prompt/token debug info, and turn the always-inline timing table into an on-demand popup.

## Purpose

The completed screen currently only offers a download link for the scored workbook — there's no way to see the actual scores/remarks without opening the file. It also never surfaces which project is even being reviewed, and the verbose prompt debug log is always inline even when the user just wants to see results. This spec adds an in-browser report table (the same per-clause detail that goes into the Excel file), a name in the header, a toggle between "Report" and "Debug info," and moves the timing breakdown into a button-triggered popup.

## 1. Backend changes

- **`project_name`**: `create_review` already computes this (from the uploaded zip's filename) before dispatching `_run_review` — it's just discarded today. Store it on state (`_new_review_state()` gains `"project_name": None`, immediately overwritten in `create_review` once the real value is known) and add it to `get_progress`'s response verbatim. Available from the very first poll, not just on completion.
- **Per-sub-criterion detail**: each entry in `category_scores` gains a `sub_criteria` list: `{id, description, score, remark}[]`. Seeded in `_new_review_state()` from the static `CATEGORIES` structure (ids known upfront, `description`/`score`/`remark` all `null`). `description` is backfilled once the template is parsed (`extract_sub_criteria_descriptions`, same timing as today's `warnings`/`test_coverage`). `score`/`remark` are backfilled per category during the scoring loop, reusing `aggregate_category_scores`'s existing `sub_scores` output (the same data already written into the Excel file — this only exposes it via the API, no new computation). Category "1"'s `"1.4"` entry gets its `score`/`remark` from the compile-check merge exactly as today; `description` comes from the template like every other sub-criterion.

### Updated API contract

```
GET /api/reviews/{review_id}/progress
  -> 200 {
       ...(all existing fields, unchanged)...
       project_name: string | null,
       category_scores: {
         id: string, name: string, percent_points: number | null,
         sub_criteria: { id: string, description: string | null, score: number | null, remark: string | null }[],
       }[],
     }
```

## 2. Frontend: project name in the header

Once `progressData.project_name` is available (from the first poll of the running screen onward), it replaces the header's title text (currently the static "Android Code Review Automation") — the description line underneath is unchanged. The idle/uploading screen keeps the current generic title, since no project is known yet.

## 3. Frontend: Report table

New `ReportTable` component, rendered on the completed screen. One section per category: a subheading (category name + its `percent_points`%), followed by a table of that category's `sub_criteria` with columns **Clause** (the id, e.g. "1.1") / **Description** / **Score** / **Remark**. Score renders as a label — `"Meets"` for `1`, `"Fails"` for `0`, `"Not evaluated"` for `null` — not the bare numeric/`null` value, matching the binary rubric's actual meaning.

## 4. Frontend: Report/Debug toggle

The bottom band — today always showing `PromptDebugLog` — becomes a two-button toggle: **Report** (default, shows `ReportTable`) and **Debug info** (shows the existing `PromptDebugLog`, unchanged). Only one is rendered at a time based on local component state. `CategoryScoresChart` and `LlmUsageStats` in the top-right are unaffected by this toggle — they stay always visible.

## 5. Frontend: Performance breakdown popup

`StatsDisplay`'s inline "Timing" card (kicker/title/table) is removed from the normal flow and replaced by a **"Performance breakdown"** ghost button placed next to the existing "Download populated workbook" button. Clicking it opens a modal — new vendored `.dialog`/`.dialog-backdrop` classes (from the same Industry stylesheet the rest of the app already draws from, not previously needed) — showing the identical Phase/Duration table, dismissable via a close button or clicking the backdrop. The table gains a row it was always missing: **"Compiling & Lint (Gradle)"** (`stats.compile_time_ms`), which has existed in the backend since the compile-check feature shipped but was never wired into this table.

## Testing

- **Backend**: extend `test_reviews_create.py` for `project_name` being set at creation and surviving through `_run_review`; extend the `category_scores` progressive-update test to also assert `sub_criteria` entries backfill `description` after analysis and `score`/`remark` per category during scoring (including the 1.4 compile-check merge case already covered). Extend `test_reviews_progress.py` for both new/extended fields round-tripping.
- **Frontend**: new `ReportTable.test.jsx` (renders per-category sections, per-clause rows, score-label mapping for 1/0/null). App-level test updates for the header showing `project_name`, the Report/Debug toggle switching visible content, and the performance popup opening/closing and including the compile/lint row.

## Out of Scope

- No change to the existing download-workbook behavior — the report table is additive, not a replacement for downloading the file.
- No change to `CategoryScoresChart`/`LlmUsageStats`/`FindingsPanel` beyond what's already implemented — they're unaffected by this spec.
- No sorting/filtering/search within the report table — a straightforward per-category, per-clause listing only.
- No change to how sub-criteria are scored or which categories exist — purely a data-exposure and UI-presentation change.

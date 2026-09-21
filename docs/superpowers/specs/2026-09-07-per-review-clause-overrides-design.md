# Per-Review Clause Checklist Overrides — Design

## Problem

Clause checklist guidance (`ClauseChecklist`: per platform + sub-clause
`checklist_text`, steering the LLM's per-clause scoring prompt) is
org-wide only today — every review for a platform uses the same guidance.
A reviewer or admin should be able to see the org defaults for the
clauses in *this specific review* and adjust some of them just for that
run, without touching the org-wide settings or persisting anywhere.

## Scope decisions (confirmed)

- The editor lives on the platform-specific review page (`AndroidReviewFlow`
  etc.), not the earlier `StartReviewDialog` — the actual clause list
  depends on which Excel template ends up in play (platform default vs. an
  uploaded custom template for this run), which isn't settled until there.
- **Partial override**: only clauses the reviewer actually edits use the
  new text for this run; every untouched clause still uses whatever's
  configured org-wide, exactly like today. Clearing a field to blank counts
  as an edit too (an explicit "no specific guidance for this clause on this
  run," distinct from never having touched it).
- Available to **reviewer + admin only**, matching who can edit the
  org-wide checklists today. The `user` role starts reviews as it already
  can, just never sees this section.
- Nothing is persisted — the override exists only as form state in the
  browser tab until the review-creation request is sent, then it's gone.

## Backend

### New endpoint: `POST /api/reviews/clause-preview`

`require_roles("admin", "reviewer")`. Multipart form: `platform` (required),
`file` (optional `.xlsx` — the reviewer's in-progress custom template
upload, if they're using one).

- Resolves the template the same way `_resolve_excel_template` already
  does: the uploaded `file` if given, else the platform's stored
  `SampleTemplate` default. 404 if neither is available (mirrors
  `create_review`'s existing "excelTemplate must be provided, or a default
  sample template configured" error).
- Runs `discover_structure` on it (same as `preview_sample_template` in
  `settings.py`) to get `categories`/`descriptions`.
- Loads the org-wide checklist dict via the existing `_load_clause_checklists()`
  (best-effort — DB outage just means no default text shown, not a hard
  failure) and merges each sub-clause's current text in.
- Response:
  ```json
  {
    "categories": [
      {
        "id": "1", "name": "Code naming conventions/ Code Structure",
        "sub_criteria": [
          {"id": "1.1", "description": "Clear and consistent naming", "checklist_text": "<org default or null>"}
        ]
      }
    ]
  }
  ```
- Invalid `.xlsx` → 400, matching `preview_sample_template`'s existing
  "Could not read this sheet's clause structure" error.

### `POST /api/reviews` gains one field

`clauseChecklistOverrides: str | None = Form(None)` — a JSON object string
`{sub_id: checklist_text}`, scoped to the request's own `platform` field
(no need to repeat platform in the keys, unlike the org-wide table's
`(platform, sub_id)` composite key). Parsed once at the top of
`create_review`; a malformed JSON string is a 400 ("clauseChecklistOverrides
must be valid JSON").

### `_run_review` merge point

After the existing `clause_checklists = await _load_clause_checklists()`
call, the parsed per-review overrides are merged on top, keyed the same
way the org-wide dict already is (`(platform, sub_id)`):

```python
for sub_id, text in clause_overrides.items():
    clause_checklists[(platform, sub_id)] = text
```

This runs *after* the best-effort org-wide load succeeds or fails, so a DB
outage on the org-wide side never wipes out an explicit per-review
override — the override is already in the request, no DB round-trip
needed for it. `score_category` itself is unchanged; it already just
consumes whatever ends up in this dict, with no awareness overrides exist.

## Frontend

- `getClausePreview({ platform, file })` in `services/api.js` — posts to
  the new endpoint, returns `categories`.
- A new `ClauseGuidanceEditor` component: given `categories` (from the
  preview call) and an `onChange(overrides)` callback, renders one
  textarea per sub-clause (grouped by category, showing each clause's
  description as a label), pre-filled with `checklist_text`. Tracks which
  fields differ from their initial value and reports only those as the
  overrides map — matching the partial-override semantics.
- Wired into `UploadForm.jsx` (the shared component `AndroidReviewFlow`
  etc. already use for the zip/template upload), gated on the current
  user's role (reviewer/admin only, via `useAuth()`), as a collapsible
  "Adjust clause guidance for this review" section. Fetches the preview
  whenever the effective template changes (default template on mount, or
  the newly-selected file when the reviewer switches to "use own
  template") — each fetch resets the editor to that template's clause
  list and org-default text, discarding any in-progress edits from a
  previously-shown template (they may not even apply to the new clause set).
- `createReview(...)` gains a `clauseChecklistOverrides` parameter,
  JSON-stringified and appended to the form data only when non-empty
  (omitted entirely otherwise, so existing behavior for reviewers who never
  touch the section is byte-for-byte unchanged).

## Testing

Backend: unit tests for the new endpoint (default template, uploaded
template, missing template 404, invalid xlsx 400, role enforcement,
org-default text correctly merged into the response) and for the
`_run_review` merge (override wins over org default for the clauses it
covers, org default untouched for the rest, override still applies when
the org-wide load is monkeypatched to fail). Frontend: `ClauseGuidanceEditor`
tests (renders clause descriptions, only reports changed fields, blanking
a field counts as changed) and `UploadForm`/review-flow tests for the
role-gated visibility and the request actually carrying the overrides field.

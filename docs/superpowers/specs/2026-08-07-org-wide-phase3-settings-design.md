# Organization-Wide Phase 3: Settings Page Design Spec

**Status:** Approved
**Date:** 2026-08-07

## Purpose

Phase 3 of the org-wide initiative (branch `org-wide-phase1-db`, still not
merged to master). Adds the settings page from the original ask: an
org-wide LLM provider default, per-platform sample review-sheet defaults,
and per-platform/per-clause checklist CRUD (replacing the hardcoded
`CLAUSE_CHECKLISTS` dict in `llm_prompts.py`). All three ship together as
one settings page.

## 1. LLM provider org default

New singleton table:
```
org_settings
  id                    integer PK (always 1)
  default_llm_provider  text
  default_ollama_model  text, nullable
  updated_at            timestamptz
```

`GET /api/settings/llm-provider` / `PUT /api/settings/llm-provider` (body:
`{default_llm_provider, default_ollama_model}`). Seeded via an Alembic data
migration with the current hardcoded default (`ollama`, no model) so
behavior doesn't change until someone edits it.

Frontend: `llmProviderStorage.js`'s hardcoded `DEFAULT_PROVIDER` fallback is
removed. `ProjectDashboardPage` fetches the org default once on load and
calls a new `initializeLlmProviderDefault(orgDefault)` helper, which seeds
`localStorage` **only if nothing's been explicitly chosen yet**
(`localStorage.getItem("llmProvider") === null`). Once a user has picked a
provider, their choice keeps sticking exactly as it does today -- this
phase only changes what an *unset* default resolves to.

## 2. Clause checklist CRUD

New table:
```
clause_checklists
  id               text PK (uuid4)
  platform         text
  sub_id           text
  checklist_text   text
  UNIQUE(platform, sub_id)
```

The existing `(".NET", "2.4")` entry is carried over via an Alembic **data**
migration (not just schema), so nothing regresses. `CLAUSE_CHECKLISTS` is
deleted from `llm_prompts.py` entirely -- fully DB-driven from here on.

`_run_review()` fetches all checklists once via a new
`crud.list_clause_checklists()` (same moment it already fetches
`sub_criteria_descriptions` from the template), builds a
`{(platform, sub_id): text}` dict, and threads it as a new parameter
through the existing call chain: `score_category()` (llm_client) ->
`ollama_client.score_category()` / `openai_client.score_category()` ->
`category_instructions()`. Mirrors exactly how `descriptions` already
flows through today. `category_instructions()` stays a pure function with
no DB awareness of its own.

API: `GET /api/settings/clause-checklists` (list all), `PUT
/api/settings/clause-checklists/{platform}/{sub_id}` (upsert), `DELETE
/api/settings/clause-checklists/{platform}/{sub_id}`.

## 3. Sample review-sheet templates

New table:
```
sample_templates
  platform      text PK
  filename      text
  file_path     text
  uploaded_at   timestamptz
```

New persistent volume `sample-templates:/data/sample-templates`, mounted
into `backend`, mirroring phase 1's `review-artifacts` pattern exactly.

API: `POST /api/settings/sample-templates/{platform}` (multipart upload,
replaces any existing default for that platform), `GET
/api/settings/sample-templates` (list configured defaults), `DELETE
/api/settings/sample-templates/{platform}`.

**Behavior change:** `create_review`'s `excelTemplate` parameter becomes
optional (`UploadFile | None = File(None)`). If the browser doesn't upload
one, the backend looks up that platform's `sample_templates` row and reads
the file server-side from `file_path`. If neither a client upload nor a
stored default exists, the existing "template must be provided" validation
error still fires.

`UploadForm.jsx` fetches the configured defaults on mount; when the
current platform has one, it shows "Using default: `<filename>`" with a
"choose a different file" control that swaps back to today's file picker.
When no default is configured for the platform, behavior is unchanged
(required picker).

## 4. Navigation

A gear icon is added to both `ProjectDashboardPage`'s own nav and the
shared `TopNav`, routing to a new `/settings` page (`SettingsPage.jsx`)
with three sections matching the above.

## Testing

- Backend: crud tests (SQLite, same pattern as phase 1/2) for
  `org_settings` get/update, `clause_checklists` list/upsert/delete,
  `sample_templates` list/upload/delete. API tests for all new endpoints.
  `test_llm_prompts.py` updated for the checklist-dict-as-parameter
  signature change (no more module-level `CLAUSE_CHECKLISTS` import).
  `test_reviews_create.py`/`test_reviews_integration.py` extended for the
  optional-`excelTemplate`-falls-back-to-stored-default path.
- Frontend: `SettingsPage.test.jsx` for all three sections.
  `UploadForm.test.jsx` extended for the "using default" / "choose
  different file" behavior. `ProjectDashboardPage.test.jsx` extended for
  the org-default-seeds-localStorage-once behavior.

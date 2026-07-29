# LLM Transparency & Layout Rework — Design Spec

**Status:** Approved
**Date:** 2026-07-28
**Source:** Team demo feedback (item 2) — show token usage and the actual prompts sent per evaluation call, and restructure the page into a 2-band layout to fit this alongside the existing progress/graph.

## Purpose

Today the review pipeline makes 6 LLM calls (5 category-scoring calls + 1 general-remarks call) but exposes none of their cost or content. This spec adds full transparency — per-call token usage and the exact prompt text sent — and reworks the page layout to surface it without cluttering the existing upload/progress/findings flow. It also fixes a real inefficiency the team flagged: today, the ~32,000-character gathered source code is resent in full on all 5 category calls.

## Backend: prompt/token capture + the caching reorder

Each category-scoring call currently sends `[{role: system, content: rubric+category-name}, {role: user, content: code}]`. The code is identical across all 5 calls; the rubric is what varies. Reordering to `[{role: system, content: code}, {role: user, content: rubric}]` makes the large, unchanging part the message-list prefix, which lets Azure OpenAI's automatic prompt caching (a real, no-code-required discount for repeated prefix tokens across nearby calls) apply — same 5 calls, same live per-category fill-in behavior, but the repeated code tokens are no longer paid for at full price if the deployment supports it. If it doesn't, this is a no-op — no regression either way. The general-remarks call is unaffected (its user message — the findings summary — is small and unique, not worth reordering).

`openai_client.py` changes:
- `score_category(...)` and `generate_general_remarks(...)` both change return shape from a bare result to `(result, prompt_info)`.
- `prompt_info = {"label": str, "prompt_text": str, "tokens": {"prompt_tokens": int|None, "completion_tokens": int|None, "total_tokens": int|None, "cached_tokens": int|None}}`.
- `prompt_text` is always the **rubric/instructions** text (the part that varies and is actually informative to review), regardless of which message role it's sent under.
- `tokens` is read from the Azure response's `usage` object (`prompt_tokens_details.cached_tokens` for the cached count, defaulting to `None` if the field isn't present).
- **Stub mode** (no `AZURE_OPENAI_KEY`) still builds and returns the real `prompt_text` via the same rubric-building helper — no network call happens, but the debug log is still previewable. `tokens` in stub mode is all zeros.

## Backend: state & API contract

`_new_review_state()` gains two fields:
- `code_context: str | None` — set once, at the same point `warnings`/`test_coverage` are first populated (right after the "analyzing" phase's `gather_code_context` call).
- `prompt_log: list` — starts empty, gets one entry appended each time a category call or the general-remarks call resolves (same live-append timing as `category_scores`'s per-category updates).

`GET /api/reviews/{review_id}/progress` gains both fields verbatim:

```
GET /api/reviews/{review_id}/progress
  -> 200 {
       ...(all existing fields, unchanged)...
       code_context: string | null,
       prompt_log: { label: string, prompt_text: string,
                     tokens: { prompt_tokens: number|null, completion_tokens: number|null,
                               total_tokens: number|null, cached_tokens: number|null } }[],
     }
```

No backend-computed totals (call count, total tokens) — the frontend derives `prompt_log.length` and sums `tokens.total_tokens` itself, so there's one source of truth.

## Frontend: layout

- **Idle screen**: unchanged — single centered upload card, 920px column.
- **Running/completed screens**: the main column widens to ~1440px (idle/error stay at 920px) and switches to a 2-band shell:
  - **Top band** (`grid-template-columns: 1fr 1fr`):
    - *Left column*: `ProgressTracker` → `FindingsPanel` → (once completed) the existing score-tags/download-button/timing-table summary from `StatsDisplay`.
    - *Right column*: `CategoryScoresChart` (same live fill-in, same "scoring step started" gating as today) → new `LlmUsageStats` (call count + total tokens, shown as `tag-outline` pills, matching existing tag styling).
  - **Bottom band**: new `PromptDebugLog` — a single card with a fixed max-height and internal vertical scroll (`overflow-y: auto`), so it doesn't grow the page as entries append live. Contents:
    1. The shared `code_context`, collapsed by default behind a "Show source code sent to the model" toggle (same expand/collapse interaction `FindingsPanel`'s cards already use).
    2. One row per `prompt_log` entry, in call order: label, its `prompt_text` (monospace, wrapped, internally scrollable if long), and its token counts (`prompt / completion / total`, plus cached if present).
  - Gated on the same "scoring step started or later" condition as the graph — nothing to show before that.
- `StatsDisplay.jsx` loses the nested `CategoryScoresChart` it was given in the previous plan (`2026-07-28-category-scores-bar-chart.md`, Task 3) — the chart now renders once, in the top band's right column, for both the running and completed states, instead of being duplicated between `App.jsx` and `StatsDisplay`.

## New components

- `LlmUsageStats.jsx` — props `{ promptLog }`. Renders two `tag-outline` pills: `"{n} LLM calls"` and `"{total} tokens used"` (sum of every entry's `tokens.total_tokens`, treating missing/null as 0).
- `PromptDebugLog.jsx` — props `{ codeContext, promptLog }`. Renders the collapsible shared code block plus the live-appending list of prompt entries described above.

## Testing

- **Backend**: `test_openai_client.py` updates throughout for the new `(result, prompt_info)` return shape on both `score_category` and `generate_general_remarks`, plus new assertions on `prompt_text` content and the reordered message roles (code as message 1, rubric as message 2) for category-scoring calls. `test_reviews_create.py`'s `score_category` monkeypatches update to return the new tuple shape. `test_reviews_progress.py` extends for `code_context`/`prompt_log` round-tripping.
- **Frontend**: new `LlmUsageStats.test.jsx` and `PromptDebugLog.test.jsx` (collapsed-by-default code block, expand toggle, per-entry rendering, live-append behavior via re-render with a longer `prompt_log`). `App.test.jsx` and `StatsDisplay.test.jsx` fixtures/assertions updated for the new fields and layout.

## Out of Scope

- No payload-size optimization for repeatedly serializing `code_context`/`prompt_log` on every 2-second poll — acceptable overhead for this POC-scale, local-network tool, consistent with the project's existing no-auth/in-memory-state scope.
- No verification that Azure's prompt caching actually engages for this specific deployment — the reorder is a safe, no-regression bet either way, not a guaranteed measured saving.
- No change to the general-remarks call's message order or content.
- No combining of the 5 category calls into one request (rejected in favor of keeping the live per-category fill-in animation).

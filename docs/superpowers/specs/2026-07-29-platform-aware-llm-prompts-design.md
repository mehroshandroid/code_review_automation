# Platform-Aware LLM Prompts — Design Spec

**Status:** Approved
**Date:** 2026-07-29
**Source:** "update the prompts like Score the following as an expert <platform e-g Android> code reviewer , so that is more focused" — followed by "may be make the prompts dynamic based on the selected platform, so when we switch to other platforms, less changes needs to be done."

## Purpose

The LLM prompts hardcode "Android" in two places (`code_context_message`, `general_remarks_prompt`) and never state the reviewer's expertise in the per-category scoring instruction itself (`category_instructions`). This round parameterizes all three by `platform`, threads that value end-to-end from the frontend's already-resolved platform selection (the same `PLATFORMS` lookup `ReviewPage` uses to route `/review/:platform`) through to the prompts — so when a future platform (iOS/.NET/Web) gets its own backend scoring path, the prompt wording adapts automatically instead of needing a find-and-replace.

## Out of Scope

- `AndroidReviewFlow`'s own UI copy (header title, description paragraph) — those are already Android-specific by the component's name and purpose; this spec only touches LLM-facing prompt text.
- Any actual iOS/.NET/Web scoring implementation — this only makes the plumbing platform-aware; `AndroidReviewFlow` is still the only flow that calls `createReview`.
- The rubric text itself (binary 0/1/null scoring, JSON response contract) — unchanged, only the reviewer-framing wording changes.

## 1. `llm_prompts.py`: parameterize by platform

Each function gains a trailing `platform: str = "Android"` parameter (default preserves every existing caller and test):

```python
def category_instructions(category_name: str, sub_criteria: list, descriptions: dict, platform: str = "Android") -> str:
    criteria_lines = "\n".join(f"{sub_id}: {descriptions.get(sub_id, '')}" for sub_id in sub_criteria)
    return (
        f"Score the following {category_name} sub-criteria as an expert {platform} code reviewer, "
        f"based ONLY on the code above:\n"
        f"{criteria_lines}\n\n"
        "For each sub-criterion, score 0 (fails), 1 (meets it), or null if the "
        "code snippet does not contain enough information to judge that specific sub-criterion "
        "(e.g. it asks about PR comments, commit history, or other context not present in "
        "source code -- do not guess or assume in that case, use null). "
        "Each remark must be specific to its own sub-criterion's exact wording above, not a "
        "general comment about the code as a whole or about a different sub-criterion.\n"
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )


def code_context_message(code_snippets: str, platform: str = "Android") -> str:
    return (
        f"You are an expert {platform} code reviewer. Here is the {platform} project's "
        f"source code for review:\n\n{code_snippets}"
    )


def general_remarks_prompt(platform: str = "Android") -> str:
    return (
        f"You are an expert {platform} code reviewer. Given per-criterion scores and remarks "
        "from a completed code review, write a concise 2-3 sentence overall summary of the "
        "code quality, highlighting the weakest areas. Respond with plain text only, no JSON."
    )
```

`build_findings_summary`, `normalize_score_result`, and `strip_markdown_fences` are unaffected — they never reference the platform.

## 2. Thread `platform` through the client layers

`openai_client.py` and `ollama_client.py`'s public `score_category`/`generate_general_remarks` (and their internal `_stub_score`/`_live_score`/`_stub_general_remarks`/`_live_general_remarks` helpers) each gain a trailing `platform: str = "Android"` parameter, passed straight through to the corresponding `llm_prompts` call:

```python
async def score_category(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, platform: str = "Android") -> tuple:
    if is_stub_mode():
        return _stub_score(category_name, sub_criteria, descriptions, platform)
    return await _live_score(category_name, sub_criteria, descriptions, code_snippets, platform)
```

(Same shape for `ollama_client.py`, alongside its existing `model` parameter.)

`llm_client.py`'s dispatcher gains the same parameter and forwards it regardless of which provider it routes to:

```python
async def score_category(
    provider: str, category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    model: str | None = None, platform: str = "Android",
) -> tuple:
    if provider == "ollama":
        return await ollama_client.score_category(category_name, sub_criteria, descriptions, code_snippets, model=model, platform=platform)
    return await openai_client.score_category(category_name, sub_criteria, descriptions, code_snippets, platform=platform)
```

`reviews.py`'s `create_review` gains a new form field, `platform: str = Form("Android")`, stored on state and threaded through `_run_review(..., platform: str = "Android")` the same way `llmProvider`/`ollamaModel`/`compileCheckMode` already are — passed into every `score_category` call in the scoring loop and the final `generate_general_remarks` call.

## 3. Frontend: send the actually-selected platform

`ReviewPage.jsx` already resolves the matching `PLATFORMS` entry for the current route (`const platform = PLATFORMS.find((p) => p.id === platformId)`) and passes it to `PlaceholderReviewFlow`. It now also passes it to `AndroidReviewFlow`:

```jsx
if (platform.id === "android") return <AndroidReviewFlow platform={platform} />;
```

`AndroidReviewFlow` accepts a `platform` prop, defaulting so its existing standalone tests (which render it directly, not through `ReviewPage`) keep working unchanged:

```jsx
export default function AndroidReviewFlow({ platform = { id: "android", label: "Android" } }) {
```

`handleUpload` sends `platform.label` as a new 6th argument:

```jsx
const result = await createReview(androidZip, excelTemplate, effectiveProvider, effectiveModel, compileCheckMode, platform.label);
```

`createReview` in `services/api.js` gains a 6th parameter, appended the same way the others are:

```js
export async function createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform) {
  // ...existing appends...
  if (platform) formData.append("platform", platform);
  // ...
}
```

## Testing

- **Backend**: extend `test_openai_client.py` and a new/extended `test_ollama_client.py` case for the `platform` parameter appearing in the built prompt text, with the default `"Android"` when omitted. Extend `test_llm_client.py` to assert `platform` is forwarded to whichever provider is routed to. Extend `test_reviews_create.py` with a test asserting `platform` is threaded from `create_review`'s form field through to `score_category`/`generate_general_remarks`.
- **Frontend**: extend `AndroidReviewFlow.test.jsx` to assert `createReview` receives `"Android"` by default and whatever label a passed-in `platform` prop carries. No changes needed to `ReviewPage.test.jsx`-equivalent coverage beyond what `App.test.jsx`'s existing `/review/android` routing test already exercises (it doesn't assert on `createReview`'s arguments, so no update is strictly required there, though the plan may add one for direct coverage of the new prop-passing).

## Ambiguity resolved during self-review

- `platform.label` (the human-readable string, e.g. `"Android"`) is what's sent to the backend and interpolated into prompt text — not `platform.id` (e.g. `"android"`) — since the prompt text is meant to read naturally ("expert Android code reviewer", not "expert android code reviewer").

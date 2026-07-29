# Compile-Check Mode Toggle — Design Spec

**Status:** Approved
**Date:** 2026-07-29
**Source:** "in android review after the files has been selected for upload as user if he wants compile time lint or static files analyses in case of static files analyses compiler will not be called and local file will be checked just like previously so its upto the reviewer to use whichever method he wants"

## Purpose

Since the compile-lint round, clause 1.4 ("No compile-time warnings") has always been scored deterministically by the real compiler service, with no way back to the original LLM-based static analysis. This round adds a reviewer-facing choice: "Compile-time lint" (today's only behavior) versus "Static file analysis" (the pre-compile-lint behavior — clause 1.4 goes back into the LLM prompt like every other sub-criterion, and the compiler service is never called). The choice is made per review, on the upload form, and persists across sessions like the LLM provider toggle.

## Out of Scope

- Any change to how clauses other than 1.4 are scored — this only affects clause 1.4's evaluation path.
- Any change to the compiler service itself (`compiler/` microservice) — "static" mode simply never calls it.
- A model/UI choice for *which* static-analysis prompt to use — static mode reuses the exact same category-scoring prompt every other sub-criterion already gets, no special-casing.

## 1. Backend: thread `compileCheckMode` through the review

`POST /api/reviews` (`create_review` in `backend/app/api/reviews.py`) gains a new form field:

```python
compileCheckMode: str = Form("compiler"),  # "compiler" | "static"
```

Stored on state (`state["compile_check_mode"]`) and threaded as a new trailing parameter into `_run_review(..., compile_check_mode: str = "compiler")`, the same way `llm_provider`/`ollama_model` already are.

Inside `_run_review`'s compiling phase, branch on the mode:

```python
t1b = time.monotonic()
state["phase"] = "compiling"
if compile_check_mode == "static":
    state["message"] = "Skipping compiler check (static analysis mode)..."
    state["lint_issues"] = []
    state["compile_status"] = "skipped"
    compile_sub_result = None
else:
    state["message"] = "Compiling and running Lint checks..."
    compile_result = await check_compile_warnings(zip_path)
    state["lint_issues"] = compile_result["issues"]
    state["compile_status"] = compile_result["status"]
    compile_sub_result = _compile_result_to_sub_score(compile_result)
stats["compile_time_ms"] = int((time.monotonic() - t1b) * 1000)
state["progress"] = 55
```

In the scoring loop, category 1's LLM sub-criteria list only excludes `"1.4"` in compiler mode:

```python
llm_sub_criteria = (
    [sub_id for sub_id in category["sub_criteria"] if sub_id != "1.4"]
    if category_id == "1" and compile_check_mode == "compiler" else category["sub_criteria"]
)
sub_results, prompt_info = await score_category(
    llm_provider, category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context,
    model=ollama_model,
)
if category_id == "1" and compile_check_mode == "compiler":
    sub_results = _merge_compile_result_into_category_1(sub_results, compile_sub_result)
```

In static mode, `"1.4"` is included in `llm_sub_criteria` and scored by the LLM exactly like `"1.1"`–`"1.3"`/`"1.5"`/`"1.6"` — same prompt, same rubric text (already keyed by `sub_criteria_descriptions["1.4"]`, which the template parser already extracts regardless of mode), no merge step needed since `sub_results` already contains a real `"1.4"` entry in the correct declared order.

A request that omits `compileCheckMode` entirely (any existing caller, any existing test) defaults to `"compiler"` — today's only behavior, unchanged.

## 2. Frontend: persistence + toggle on `UploadForm`

New `frontend/src/services/compileCheckModeStorage.js`, mirroring `llmProviderStorage.js`'s shape exactly:

```js
const STORAGE_KEY = "compileCheckMode";
const DEFAULT_MODE = "compiler";

export function getCompileCheckMode() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_MODE;
}

export function setCompileCheckMode(mode) {
  localStorage.setItem(STORAGE_KEY, mode);
}
```

`UploadForm` gains a two-button toggle, always visible above the submit button, alongside the two file pickers:

```jsx
<div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
  <button
    type="button"
    className={`btn ${compileCheckMode === "compiler" ? "btn-primary" : ""}`}
    onClick={() => handleSelectMode("compiler")}
  >
    Compile-time lint
  </button>
  <button
    type="button"
    className={`btn ${compileCheckMode === "static" ? "btn-primary" : ""}`}
    onClick={() => handleSelectMode("static")}
  >
    Static file analysis
  </button>
</div>
```

`compileCheckMode` is local component state initialized from `getCompileCheckMode()`; `handleSelectMode` calls `setCompileCheckMode(mode)` and updates that state so the highlighted button updates immediately — the same read-on-mount/write-on-click pattern `HomePage` already uses for the LLM provider toggle. Clicking it does **not** route through `onSubmit`: `UploadForm`'s `onSubmit(androidZip, excelTemplate)` signature is unchanged. Instead, `AndroidReviewFlow.handleUpload` reads `getCompileCheckMode()` directly at submit time, the same way it already reads `getLlmProvider()`/`getOllamaModel()`.

## 3. `createReview` gains the field + `FindingsPanel` handles `"skipped"`

`createReview` in `frontend/src/services/api.js` gains a 5th parameter, appended the same way `ollamaModel` already is:

```js
export async function createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode) {
  const formData = new FormData();
  formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}
```

`AndroidReviewFlow.handleUpload` passes `getCompileCheckMode()` as the new 5th argument.

`FindingsPanel`'s `lintCardProps` (`frontend/src/components/FindingsPanel.jsx`) gains a case for the new status, checked before the existing fallback:

```js
function lintCardProps(compileStatus, lintIssues) {
  if (compileStatus === "ok") { /* ...unchanged... */ }
  if (compileStatus === "build_failed") { /* ...unchanged... */ }
  if (compileStatus === "unavailable") { /* ...unchanged... */ }
  if (compileStatus === "skipped") {
    return { value: "—", caption: "Static analysis mode selected — clause 1.4 scored by AI.", expandable: false };
  }
  return { value: "—", caption: "Not yet checked.", expandable: false };
}
```

No changes to `ProgressTracker` (the existing phase-message display already shows whatever `state["message"]` is set to per mode) or `ReportTable` (clause 1.4 gets a real `description`/`score`/`remark` from the LLM in static mode via the existing sub-criteria backfill, identical in shape to every other sub-criterion).

## Testing

- **Backend**: extend `test_reviews_create.py` with a new test asserting that in `"static"` mode, `check_compile_warnings` is never called, `"1.4"` is included in the sub-criteria sent to `score_category`, `compile_status` ends up `"skipped"`, and `lint_issues` stays `[]`. The existing compiler-mode test (`test_run_review_scores_1_4_from_compile_check_and_excludes_it_from_the_llm`) already calls `_run_review` without passing `compile_check_mode`, so it continues to exercise the `"compiler"` default unchanged — no edit needed there. Extend `test_reviews_integration.py`'s stub-mode pipeline test with a static-mode variant confirming `"1.4"` receives a real stub score instead of a compile-derived one.
- **Frontend**: new `compileCheckModeStorage.test.jsx` (mirrors `llmProviderStorage.test.jsx`); extend `UploadForm.test.jsx` for the toggle's default/highlight/persistence behavior; extend `AndroidReviewFlow.test.jsx` to assert `createReview` receives the persisted mode; extend `FindingsPanel.test.jsx` for the new `"skipped"` caption.

## Ambiguity resolved during self-review

- "Static file analysis" reuses the exact existing category-scoring prompt for clause 1.4 (same rubric text, same JSON response contract) — there is no separate "static analysis prompt." The only behavioral difference from compiler mode is which sub-criteria list gets sent to the LLM and whether the compiler service is called at all.

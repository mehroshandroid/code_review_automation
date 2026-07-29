# Local Ollama LLM Provider — Design Spec

**Status:** Approved
**Date:** 2026-07-29
**Source:** "now lets work on using local model... recommend which model is good..." followed by "brainstorm and check ollama downloaded models as well, i think mistral is downloaded" — making the previously cosmetic Azure/Ollama toggle (added in the multi-platform landing page round) actually control which LLM scores a review.

## Purpose

The landing page already has an Azure OpenAI / Ollama (local) toggle that persists to `localStorage` but has never influenced an actual request — every review still goes to Azure regardless of the selection. This round wires it up end to end: a real Ollama-backed scoring path in the backend, a per-review provider (and model) selection that travels from the browser to the backend, and a model picker driven by what's actually installed via `ollama list`.

## Out of Scope

- Any change to Azure OpenAI's behavior, prompts, or rubric — this round only adds a second, real path alongside it.
- Auto-pulling models the user hasn't downloaded — the model dropdown only ever shows what `ollama list` already reports; pulling a new model is a manual `ollama pull` step outside this app.
- Any UI for configuring `OLLAMA_BASE_URL` itself — it's a backend deployment concern (docker-compose env var), not a per-review user choice.

## 1. Backend refactor: shared prompt logic, `ollama_client.py`, provider dispatcher

`app/analyzer/openai_client.py`'s prompt-building and response-parsing helpers — `_category_instructions`, `_code_context_message`, `_general_remarks_prompt`, `_build_findings_summary`, `_normalize_score_result`, `_strip_markdown_fences` — are provider-agnostic. They move, unrenamed apart from dropping the leading underscore (since they're now a module's public surface, not another module's private helpers), into a new `app/analyzer/llm_prompts.py`:

```python
def category_instructions(category_name: str, sub_criteria: list, descriptions: dict) -> str: ...
def code_context_message(code_snippets: str) -> str: ...
def general_remarks_prompt() -> str: ...
def build_findings_summary(category_results: dict) -> str: ...
def normalize_score_result(parsed: dict, sub_criteria: list) -> dict: ...
def strip_markdown_fences(content: str) -> str: ...
```

`openai_client.py` imports these from `llm_prompts` instead of defining them locally. Its public functions (`score_category`, `generate_general_remarks`, `is_stub_mode`) keep their exact current signatures and behavior — every one of `test_openai_client.py`'s 15 existing tests keeps passing unmodified, since none of them reach into the (now-relocated) private helpers directly.

New `app/analyzer/ollama_client.py`, mirroring `openai_client.py`'s live-call shape but targeting Ollama's OpenAI-compatible endpoint:

```python
DEFAULT_OLLAMA_BASE_URL = "http://host.docker.internal:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"

async def score_category(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, model: str | None = None) -> tuple:
    ...

async def generate_general_remarks(category_results: dict, model: str | None = None) -> tuple:
    ...

async def list_models() -> list[str]:
    ...
```

`score_category`/`generate_general_remarks` build the same message shape as `openai_client.py` (via the shared `llm_prompts` helpers), POST to `{OLLAMA_BASE_URL}/v1/chat/completions` with `{"model": model or DEFAULT_OLLAMA_MODEL, "messages": [...], "temperature": 0.3, "response_format": {"type": "json_object"}}` (mirroring Azure's payload; harmless if a given Ollama version ignores `response_format`, since the existing markdown-fence-stripping + malformed-response fallback already tolerates a plain-text reply), and parse the response identically. `OLLAMA_BASE_URL` is read from the `OLLAMA_BASE_URL` environment variable (falling back to `DEFAULT_OLLAMA_BASE_URL`), matching `compile_checker.py`'s `COMPILER_SERVICE_URL` pattern. There is no retry-on-429 logic (no rate limiting on a local server) — any failure (connection refused, timeout, non-200, malformed JSON) is caught and returns the same fallback shape Azure's client already returns on failure: `{sub_id: {"score": None, "remark": ""}}` for scoring, `""` for general remarks, and `_empty_tokens()`-shaped usage. `_run_review` never needs to know which provider actually ran.

`list_models()` calls `GET {OLLAMA_BASE_URL}/api/tags`, returning `[model["name"] for model in response.json()["models"]]`. On any failure, returns `[]` — never raises, matching `check_compile_warnings`'s never-raise pattern.

`docker-compose.yml`'s `backend` service gains two explicit environment lines, matching the existing `COMPILER_SERVICE_URL=http://compiler:8000` convention (set explicitly even though it matches the Python-side default, so the value is discoverable without reading source):

```yaml
- OLLAMA_BASE_URL=http://host.docker.internal:11434
- OLLAMA_MODEL=qwen2.5-coder:7b
```

New thin `app/analyzer/llm_client.py`, the only module `reviews.py` imports from now:

```python
async def score_category(provider: str, category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, model: str | None = None) -> tuple:
    if provider == "ollama":
        return await ollama_client.score_category(category_name, sub_criteria, descriptions, code_snippets, model=model)
    return await openai_client.score_category(category_name, sub_criteria, descriptions, code_snippets)

async def generate_general_remarks(provider: str, category_results: dict, model: str | None = None) -> tuple:
    if provider == "ollama":
        return await ollama_client.generate_general_remarks(category_results, model=model)
    return await openai_client.generate_general_remarks(category_results)
```

Any `provider` value other than the literal string `"ollama"` (including `None`, `"azure"`, or anything unrecognized) routes to `openai_client` — today's only behavior, preserved as the default.

## 2. Per-review provider selection reaches the backend

`POST /api/reviews` (`create_review` in `app/api/reviews.py`) gains two new optional form fields:

```python
async def create_review(
    androidZip: UploadFile = File(...),
    excelTemplate: UploadFile = File(...),
    llmProvider: str = Form("azure"),
    ollamaModel: str | None = Form(None),
):
```

Both are stored on the review's state (`state["llm_provider"]`, `state["ollama_model"]`) and threaded as two new trailing parameters into `_run_review(..., llm_provider, ollama_model)`. Inside `_run_review`, every existing call site is updated to pass them through:

```python
sub_results, prompt_info = await score_category(
    llm_provider, category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context, model=ollama_model
)
...
general_remarks, remarks_prompt_info = await generate_general_remarks(llm_provider, scores_by_category, model=ollama_model)
```

A request that omits both fields entirely (any existing caller, any existing test) behaves exactly as today: `llmProvider` defaults to `"azure"`, `ollamaModel` defaults to `None` and is ignored by the Azure path.

## 3. New `/api/ollama/models` endpoint

```python
@router.get("/api/ollama/models")
async def list_ollama_models():
    return {"models": await ollama_client.list_models()}
```

Always returns `200` with a (possibly empty) list — there is no error case from the caller's perspective, matching `list_models()`'s never-raise contract. The frontend uses this to populate the model dropdown and to decide whether "Ollama (local)" should be enabled at all (Section 4).

## 4. Frontend: HomePage provider toggle + model dropdown, with gating

`HomePage` fetches `GET /api/ollama/models` once on mount (via a new `getOllamaModels()` in `frontend/src/services/api.js`, following the existing `axios.get` pattern). While the request is in flight, the toggle renders using whatever was last in `localStorage` (no layout flash). Once it resolves:

- **Non-empty list:** "Ollama (local)" is enabled. A `<select>` of the returned model names appears directly beneath the toggle whenever Ollama is the currently-selected provider — defaulting to the persisted `ollamaModel` value if it's still present in the list, otherwise the first entry. Selecting a different model calls a new `setOllamaModel()` (Section below) immediately.
- **Empty list:** "Ollama (local)" renders `disabled` (grayed out, `pointer-events: none` via a disabled `<button>`), no dropdown is shown, and the *effective* provider for this page/session is forced to `"azure"` — even if `localStorage` currently holds `"ollama"` from an earlier session where models existed. The stored preference itself is left untouched (not overwritten), so it's honored again automatically once a model is pulled and the page reloads.

Default provider (only when nothing is yet in `localStorage`): now `"ollama"`, not `"azure"` — `llmProviderStorage.js`'s `DEFAULT_PROVIDER` constant changes from `"azure"` to `"ollama"`. This only matters when the models list is non-empty; the empty-list case still forces `"azure"` regardless.

`llmProviderStorage.js` gains two more exports, following the existing `getLlmProvider`/`setLlmProvider` shape:

```js
const MODEL_STORAGE_KEY = "ollamaModel";

export function getOllamaModel() {
  return localStorage.getItem(MODEL_STORAGE_KEY) || null;
}

export function setOllamaModel(model) {
  localStorage.setItem(MODEL_STORAGE_KEY, model);
}
```

## 5. Frontend: sending provider + model through to the actual review request

`AndroidReviewFlow`'s `handleUpload` reads the persisted provider and model at submit time, re-applying the same empty-models fallback used on the home page (fetching `GET /api/ollama/models` again — cheap, avoids threading fetched state between pages — and forcing `"azure"` if the list is empty even though `localStorage` says `"ollama"`), then passes both through:

```js
const result = await createReview(androidZip, excelTemplate, effectiveProvider, effectiveProvider === "ollama" ? effectiveModel : null);
```

`createReview` in `services/api.js` gains two new optional parameters, appended as extra fields on the existing multipart form:

```js
export async function createReview(androidZip, excelTemplate, llmProvider, ollamaModel) {
  const formData = new FormData();
  formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}
```

Existing callers/tests that invoke `createReview(androidZip, excelTemplate)` with only two arguments are unaffected — the new fields are simply omitted from the form, and the backend's `Form("azure")`/`Form(None)` defaults apply exactly as in Section 2.

## Testing

- **`llm_prompts.py`**: no new dedicated tests — behavior is already fully exercised indirectly through `test_openai_client.py` (unchanged) once its helpers are just re-exports of the shared module.
- **`ollama_client.py`**: new `test_ollama_client.py`, mirroring `test_openai_client.py`'s monkeypatch-`httpx.AsyncClient.post` style — success parsing, malformed-response fallback, connection-error fallback, `model` parameter overriding the default, and `list_models()` success/empty/failure cases.
- **`llm_client.py`**: new `test_llm_client.py` — `provider == "ollama"` routes to `ollama_client` (verified via monkeypatch), any other value (including omitted/`None`) routes to `openai_client`.
- **`reviews.py`**: extend `test_reviews_create.py` to assert `llm_provider`/`ollama_model` are stored on state at creation and passed through to the scoring calls (monkeypatching `llm_client.score_category` the way tests currently monkeypatch `score_category`).
- **Frontend**: extend `llmProviderStorage.test.jsx` for the new model getter/setter and the changed default; extend `HomePage.test.jsx` for the enabled/disabled toggle states and the model dropdown; extend `AndroidReviewFlow.test.jsx` (or add a new focused test) to assert `createReview` is called with the resolved provider/model.

## Ambiguity resolved during self-review

- "Auto selected" (empty-models case) means forcing the *effective* provider for that page load, not silently rewriting the user's stored preference — so a real fix (pulling a model) restores their original choice without them having to re-select it.
- `ollamaModel` is only ever sent to the backend when the effective provider is `"ollama"` — sending it alongside `"azure"` would be meaningless and is explicitly guarded against in both the request-building code (Section 5) and the backend's dispatcher (Section 1, which only reads `model` on the Ollama branch).

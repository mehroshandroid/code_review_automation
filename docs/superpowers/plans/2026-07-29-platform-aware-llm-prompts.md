# Platform-Aware LLM Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parameterize the LLM prompt text by `platform` (default `"Android"`) so the "expert Android code reviewer" framing — currently hardcoded in two places and absent from the per-category scoring instruction — becomes data-driven, threaded end-to-end from the frontend's already-resolved platform selection.

**Architecture:** `llm_prompts.py`'s three prompt-building functions gain a trailing `platform` parameter; `openai_client.py`/`ollama_client.py` and the `llm_client.py` dispatcher forward it; `reviews.py` gains a new `platform` form field threaded through `_run_review` into every scoring call; the frontend's `ReviewPage` passes its already-resolved platform object into `AndroidReviewFlow`, which sends `platform.label` with the review.

**Tech Stack:** FastAPI/Python backend (pytest, pytest-asyncio), React 19 frontend (Jest/React Testing Library). No new dependencies.

## Global Constraints

- `platform` defaults to `"Android"` everywhere it's threaded — every existing caller/test that omits it keeps behaving exactly as today.
- `platform.label` (the human-readable string, e.g. `"Android"`) is what's sent and interpolated into prompt text — never `platform.id` (e.g. `"android"`).
- The rubric text itself (binary 0/1/null scoring, JSON response contract) is unchanged — only the reviewer-framing wording changes.
- `AndroidReviewFlow`'s own UI copy (header title, description paragraph) is out of scope — this only touches LLM-facing prompt text and the plumbing that carries `platform` to it.
- TDD throughout: write the failing test, run it and confirm the failure, implement, run again and confirm the pass, then commit.

---

## Task 1: `llm_prompts.py` + `openai_client.py`

**Files:**
- Modify: `backend/app/analyzer/llm_prompts.py`
- Modify: `backend/app/analyzer/openai_client.py`
- Modify: `backend/tests/test_openai_client.py`

**Interfaces:**
- Produces: `category_instructions(category_name, sub_criteria, descriptions, platform="Android") -> str`, `code_context_message(code_snippets, platform="Android") -> str`, `general_remarks_prompt(platform="Android") -> str`; `openai_client.score_category(category_name, sub_criteria, descriptions, code_snippets, platform="Android") -> tuple`, `openai_client.generate_general_remarks(category_results, platform="Android") -> tuple`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_openai_client.py` (after `test_stub_mode_returns_placeholder_scores`):

```python
@pytest.mark.asyncio
async def test_stub_mode_defaults_platform_to_android(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    _, prompt_info = await openai_client.score_category("Code Structure", ["1.1"], {}, "code here")
    assert "as an expert Android code reviewer" in prompt_info["prompt_text"]
```

Add after `test_live_mode_calls_azure_endpoint_and_parses_response`:

```python
@pytest.mark.asyncio
async def test_live_mode_sends_the_provided_platform_in_both_prompt_messages(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "ok"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _, prompt_info = await openai_client.score_category("Code Structure", ["1.1"], {}, "code here", platform="iOS")

    assert "as an expert iOS code reviewer" in prompt_info["prompt_text"]
    assert "expert iOS code reviewer" in captured["json"]["messages"][0]["content"]
```

Add after `test_generate_general_remarks_live_mode`:

```python
@pytest.mark.asyncio
async def test_generate_general_remarks_sends_the_provided_platform(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        content = "Overall summary."
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _, prompt_info = await openai_client.generate_general_remarks({}, platform="iOS")

    assert "expert iOS code reviewer" in prompt_info["prompt_text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_openai_client.py -v`
Expected: FAIL — the 3 new tests fail with `TypeError: score_category() got an unexpected keyword argument 'platform'` (and similarly for `generate_general_remarks`); the other 14 tests still pass.

- [ ] **Step 3: Implement**

Overwrite `backend/app/analyzer/llm_prompts.py`:

```python
import re


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


def build_findings_summary(category_results: dict) -> str:
    lines = []
    for result in category_results.values():
        for sub_id, sub in result["sub_scores"].items():
            lines.append(f"{sub_id}: score={sub.get('score')}, remark={sub.get('remark') or ''}")
    return "\n".join(lines) if lines else "No findings were scored."


def normalize_score_result(parsed: dict, sub_criteria: list) -> dict:
    """Guarantees the returned dict has exactly sub_criteria's keys, in that
    exact order -- regardless of what order (or completeness) the model's
    JSON used. Callers rely on this order to align each sub-criterion's
    score/remark to the correct row when writing the Excel output
    positionally; a model that reorders, skips, or hallucinates an extra key
    would otherwise silently misalign every row after the discrepancy.
    """
    result = {}
    for sub_id in sub_criteria:
        entry = parsed.get(sub_id) if isinstance(parsed, dict) else None
        if isinstance(entry, dict):
            result[sub_id] = {"score": entry.get("score"), "remark": entry.get("remark", "")}
        else:
            result[sub_id] = {"score": None, "remark": ""}
    return result


def strip_markdown_fences(content: str) -> str:
    """Defensive fallback: response_format=json_object should prevent this, but
    strip a ```json ... ``` or ``` ... ``` wrapper if the model adds one anyway.
    """
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return match.group(1) if match else content
```

In `backend/app/analyzer/openai_client.py`, update the public functions and every internal helper that builds prompt text:

```python
async def score_category(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, platform: str = "Android") -> tuple:
    if is_stub_mode():
        return _stub_score(category_name, sub_criteria, descriptions, platform)
    return await _live_score(category_name, sub_criteria, descriptions, code_snippets, platform)


async def generate_general_remarks(category_results: dict, platform: str = "Android") -> tuple:
    if is_stub_mode():
        return _stub_general_remarks(platform)
    return await _live_general_remarks(category_results, platform)


def _stub_score(category_name: str, sub_criteria: list, descriptions: dict, platform: str = "Android") -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform)
    sub_results = {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _zero_tokens()}
    return sub_results, prompt_info


def _stub_general_remarks(platform: str = "Android") -> tuple:
    text = f"{STUB_PREFIX} No Azure OpenAI key configured; general remarks not generated."
    prompt_info = {"label": "General remarks", "prompt_text": general_remarks_prompt(platform), "tokens": _zero_tokens()}
    return text, prompt_info
```

```python
async def _live_score(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, platform: str = "Android") -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform)
    payload = {
        "messages": [
            {"role": "system", "content": code_context_message(code_snippets, platform)},
            {"role": "user", "content": instructions},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}

    response = await _post_with_retry(payload)
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _extract_usage(response)}
    if response is None:
        return fallback, prompt_info

    try:
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(strip_markdown_fences(content))
        return normalize_score_result(parsed, sub_criteria), prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return fallback, prompt_info


async def _live_general_remarks(category_results: dict, platform: str = "Android") -> tuple:
    system_prompt = general_remarks_prompt(platform)
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_findings_summary(category_results)},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }

    response = await _post_with_retry(payload)
    prompt_info = {"label": "General remarks", "prompt_text": system_prompt, "tokens": _extract_usage(response)}
    if response is None:
        return "", prompt_info

    try:
        text = response.json()["choices"][0]["message"]["content"].strip()
        return text, prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return "", prompt_info
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_openai_client.py -v`
Expected: PASS — all 17 tests green (14 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/llm_prompts.py backend/app/analyzer/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: parameterize LLM prompts by platform (default Android)"
```

---

## Task 2: `ollama_client.py`

**Files:**
- Modify: `backend/app/analyzer/ollama_client.py`
- Modify: `backend/tests/test_ollama_client.py`

**Interfaces:**
- Consumes: `category_instructions`, `code_context_message`, `general_remarks_prompt` (Task 1, all now accepting `platform`).
- Produces: `ollama_client.score_category(category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android") -> tuple`, `ollama_client.generate_general_remarks(category_results, model=None, platform="Android") -> tuple`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_ollama_client.py` (after `test_score_category_uses_the_model_override_when_provided`):

```python
@pytest.mark.asyncio
async def test_score_category_sends_the_provided_platform(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "ok"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await ollama_client.score_category("Code Structure", ["1.1"], {}, "code here", platform="iOS")

    assert "expert iOS code reviewer" in captured["json"]["messages"][0]["content"]
    assert "as an expert iOS code reviewer" in captured["json"]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_score_category_defaults_platform_to_android(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "ok"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await ollama_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert "expert Android code reviewer" in captured["json"]["messages"][0]["content"]
```

Add after `test_generate_general_remarks_calls_ollama_and_parses_text`:

```python
@pytest.mark.asyncio
async def test_generate_general_remarks_sends_the_provided_platform(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["json"] = json
        content = "Overall summary."
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await ollama_client.generate_general_remarks({}, platform="iOS")

    assert "expert iOS code reviewer" in captured["json"]["messages"][0]["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_ollama_client.py -v`
Expected: FAIL — `TypeError: score_category() got an unexpected keyword argument 'platform'` (and similarly for `generate_general_remarks`).

- [ ] **Step 3: Implement**

In `backend/app/analyzer/ollama_client.py`, update `score_category` and `generate_general_remarks`:

```python
async def score_category(
    category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    model: str | None = None, platform: str = "Android",
) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform)
    payload = {
        "model": _model(model),
        "messages": [
            {"role": "system", "content": code_context_message(code_snippets, platform)},
            {"role": "user", "content": instructions},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}

    response = await _post(payload)
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _extract_usage(response)}
    if response is None:
        return fallback, prompt_info

    try:
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(strip_markdown_fences(content))
        return normalize_score_result(parsed, sub_criteria), prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return fallback, prompt_info


async def generate_general_remarks(category_results: dict, model: str | None = None, platform: str = "Android") -> tuple:
    system_prompt = general_remarks_prompt(platform)
    payload = {
        "model": _model(model),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_findings_summary(category_results)},
        ],
        "temperature": 0.3,
    }

    response = await _post(payload)
    prompt_info = {"label": "General remarks", "prompt_text": system_prompt, "tokens": _extract_usage(response)}
    if response is None:
        return "", prompt_info

    try:
        text = response.json()["choices"][0]["message"]["content"].strip()
        return text, prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return "", prompt_info
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_ollama_client.py -v`
Expected: PASS — all 10 tests green (8 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/ollama_client.py backend/tests/test_ollama_client.py
git commit -m "feat: thread platform through ollama_client.py"
```

---

## Task 3: `llm_client.py` dispatcher

**Files:**
- Modify: `backend/app/analyzer/llm_client.py`
- Modify: `backend/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `openai_client.score_category`/`generate_general_remarks` (Task 1, now accepting `platform`); `ollama_client.score_category`/`generate_general_remarks` (Task 2, now accepting `platform`).
- Produces: `llm_client.score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android") -> tuple`, `llm_client.generate_general_remarks(provider, category_results, model=None, platform="Android") -> tuple`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_llm_client.py`, at the end of the file:

```python
@pytest.mark.asyncio
async def test_score_category_forwards_platform_to_whichever_provider_is_routed_to(monkeypatch):
    captured_ollama = {}
    captured_openai = {}

    async def fake_ollama_score_category(category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
        captured_ollama["platform"] = platform
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    async def fake_openai_score_category(category_name, sub_criteria, descriptions, code_snippets, platform="Android"):
        captured_openai["platform"] = platform
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "score_category", fake_ollama_score_category)
    monkeypatch.setattr(llm_client.openai_client, "score_category", fake_openai_score_category)

    await llm_client.score_category("ollama", "Code Structure", ["1.1"], {}, "code", platform="iOS")
    await llm_client.score_category("azure", "Code Structure", ["1.1"], {}, "code", platform="iOS")

    assert captured_ollama["platform"] == "iOS"
    assert captured_openai["platform"] == "iOS"


@pytest.mark.asyncio
async def test_generate_general_remarks_forwards_platform_to_whichever_provider_is_routed_to(monkeypatch):
    captured_ollama = {}
    captured_openai = {}

    async def fake_ollama_general_remarks(category_results, model=None, platform="Android"):
        captured_ollama["platform"] = platform
        return "ollama summary", {"label": "General remarks", "prompt_text": "x", "tokens": {}}

    async def fake_openai_general_remarks(category_results, platform="Android"):
        captured_openai["platform"] = platform
        return "azure summary", {"label": "General remarks", "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "generate_general_remarks", fake_ollama_general_remarks)
    monkeypatch.setattr(llm_client.openai_client, "generate_general_remarks", fake_openai_general_remarks)

    await llm_client.generate_general_remarks("ollama", {"1": {}}, platform="iOS")
    await llm_client.generate_general_remarks("azure", {"1": {}}, platform="iOS")

    assert captured_ollama["platform"] == "iOS"
    assert captured_openai["platform"] == "iOS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `TypeError: score_category() got an unexpected keyword argument 'platform'` (the dispatcher doesn't accept or forward it yet).

- [ ] **Step 3: Implement**

Overwrite `backend/app/analyzer/llm_client.py`:

```python
from app.analyzer import ollama_client, openai_client


async def score_category(
    provider: str, category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    model: str | None = None, platform: str = "Android",
) -> tuple:
    if provider == "ollama":
        return await ollama_client.score_category(
            category_name, sub_criteria, descriptions, code_snippets, model=model, platform=platform
        )
    return await openai_client.score_category(category_name, sub_criteria, descriptions, code_snippets, platform=platform)


async def generate_general_remarks(provider: str, category_results: dict, model: str | None = None, platform: str = "Android") -> tuple:
    if provider == "ollama":
        return await ollama_client.generate_general_remarks(category_results, model=model, platform=platform)
    return await openai_client.generate_general_remarks(category_results, platform=platform)
```

Now update the 4 pre-existing fake functions in `backend/tests/test_llm_client.py` so they tolerate the `platform` keyword the dispatcher now always passes (each appears once — add `, platform="Android"` to each signature, unused in the body):

```python
    async def fake_ollama_score_category(category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
```

```python
    async def fake_openai_score_category(category_name, sub_criteria, descriptions, code_snippets, platform="Android"):
```

```python
    async def fake_ollama_general_remarks(category_results, model=None, platform="Android"):
```

```python
    async def fake_openai_general_remarks(category_results, platform="Android"):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_llm_client.py -v`
Expected: PASS — all 6 tests green (4 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/llm_client.py backend/tests/test_llm_client.py
git commit -m "feat: thread platform through the llm_client.py dispatcher"
```

---

## Task 4: `reviews.py` wiring

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/tests/test_reviews_create.py`
- Modify: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `llm_client.score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android")`, `llm_client.generate_general_remarks(provider, category_results, model=None, platform="Android")` (Task 3).
- Produces: `POST /api/reviews` accepts `platform` (form field, default `"Android"`); `_run_review` gains a `platform: str = "Android"` parameter.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_reviews_create.py` (placed after `test_run_review_passes_llm_provider_and_model_through_to_scoring_calls`):

```python
async def test_run_review_passes_platform_through_to_scoring_calls(monkeypatch):
    review_id = "platform-threading-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_platforms = []

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
        captured_platforms.append(platform)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_generate_general_remarks(provider, category_results, model=None, platform="Android"):
        captured_platforms.append(platform)
        return "summary", {"label": "General remarks", "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "generate_general_remarks", fake_generate_general_remarks)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform="iOS",
    )

    # 5 category calls + 1 general-remarks call, all carrying the same platform.
    assert captured_platforms == ["iOS"] * 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py::test_run_review_passes_platform_through_to_scoring_calls -v`
Expected: FAIL — `TypeError: _run_review() got an unexpected keyword argument 'platform'`.

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, add the new form field to `create_review`:

```python
@router.post("/api/reviews")
async def create_review(
    androidZip: UploadFile = File(...),
    excelTemplate: UploadFile = File(...),
    llmProvider: str = Form("azure"),
    ollamaModel: str | None = Form(None),
    compileCheckMode: str = Form("compiler"),
    platform: str = Form("Android"),
):
```

Pass it through to `_run_review`:

```python
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel, compileCheckMode, platform,
        )
    )
```

Add the new parameter to `_run_review`'s signature:

```python
async def _run_review(
    review_id: str,
    work_dir: Path,
    zip_path: Path,
    template_path: Path,
    zip_valid: bool,
    template_valid: bool,
    project_name: str,
    llm_provider: str = "azure",
    ollama_model: str | None = None,
    compile_check_mode: str = "compiler",
    platform: str = "Android",
) -> None:
```

Update the scoring-loop call site:

```python
            sub_results, prompt_info = await score_category(
                llm_provider, category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context,
                model=ollama_model, platform=platform,
            )
```

Update the general-remarks call site:

```python
        general_remarks, remarks_prompt_info = await generate_general_remarks(
            llm_provider, scores_by_category, model=ollama_model, platform=platform
        )
```

Now update the pre-existing fake `score_category` functions across both test files so they tolerate the `platform` keyword `_run_review` now always passes. In `backend/tests/test_reviews_create.py`, this exact signature appears twice (in `test_run_review_updates_message_per_category_during_scoring` and `test_run_review_updates_category_scores_progressively`) — update both occurrences:

```python
    async def _recording_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
```

This exact signature appears three times (in `test_run_review_passes_llm_provider_and_model_through_to_scoring_calls`, `test_run_review_scores_1_4_from_compile_check_and_excludes_it_from_the_llm`, and `test_run_review_static_mode_skips_compiler_and_scores_1_4_via_llm`) — update all three occurrences:

```python
    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
```

This appears once (in `test_run_review_passes_llm_provider_and_model_through_to_scoring_calls`) — update it:

```python
    async def fake_generate_general_remarks(provider, category_results, model=None, platform="Android"):
```

In `backend/tests/test_reviews_integration.py`, update `_capturing_score_category`:

```python
    async def _capturing_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
        captured_code_snippets.append(code_snippets)
        return await real_score_category(
            provider, category_name, sub_criteria, descriptions, code_snippets, model=model, platform=platform
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py tests/test_reviews_integration.py -v`
Expected: PASS — all tests in both files green, including the new threading test.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: PASS — full backend suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_integration.py
git commit -m "feat: thread platform from the review request through every scoring call"
```

---

## Task 5: Frontend — send the actually-selected platform

**Files:**
- Modify: `frontend/src/pages/ReviewPage.jsx`
- Modify: `frontend/src/pages/AndroidReviewFlow.jsx`
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/AndroidReviewFlow.test.jsx`
- Modify: `frontend/src/services/api.test.js`

**Interfaces:**
- Produces: `createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform)` — the 6th parameter is new and optional. `AndroidReviewFlow({ platform })` — new prop, defaults to `{ id: "android", label: "Android" }`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/pages/AndroidReviewFlow.test.jsx`, update the three existing `toHaveBeenCalledWith` assertions to add a 6th expected argument, `"Android"` (the default label, since none of these tests pass a `platform` prop):

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b", "compiler", "Android");
```

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "Android");
```

```jsx
  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "static", "Android");
```

Then add a new test at the end of the file:

```jsx
test("sends the platform label from a custom platform prop instead of the default", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  render(
    <MemoryRouter>
      <AndroidReviewFlow platform={{ id: "android", label: "AndroidCustom" }} />
    </MemoryRouter>
  );
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null, "compiler", "AndroidCustom");
});
```

Add to `frontend/src/services/api.test.js`, inside the `describe("createReview", ...)` block:

```js
  it("includes platform field when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "azure", null, "compiler", "Android");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("platform")).toBe("Android");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx src/services/api.test.js`
Expected: FAIL — `createReview` is still called with only 5 arguments (the updated assertions and new tests all fail); `formData.get("platform")` is `null`.

- [ ] **Step 3: Implement**

In `frontend/src/pages/ReviewPage.jsx`, pass `platform` into `AndroidReviewFlow`:

```jsx
  if (!platform) return <Navigate to="/" replace />;
  if (platform.id === "android") return <AndroidReviewFlow platform={platform} />;
  return <PlaceholderReviewFlow platform={platform} />;
```

In `frontend/src/pages/AndroidReviewFlow.jsx`, accept the prop with a default and thread it through `handleUpload`:

```jsx
export default function AndroidReviewFlow({ platform = { id: "android", label: "Android" } }) {
```

```jsx
      const compileCheckMode = getCompileCheckMode();

      const result = await createReview(
        androidZip, excelTemplate, effectiveProvider, effectiveModel, compileCheckMode, platform.label
      );
```

In `frontend/src/services/api.js`, update `createReview`:

```js
export async function createReview(androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform) {
  const formData = new FormData();
  formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  if (platform) formData.append("platform", platform);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx src/services/api.test.js`
Expected: PASS — all tests green.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test`
Expected: PASS — full frontend suite green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ReviewPage.jsx frontend/src/pages/AndroidReviewFlow.jsx frontend/src/services/api.js frontend/src/pages/AndroidReviewFlow.test.jsx frontend/src/services/api.test.js
git commit -m "feat: send the actually-selected platform label with the review"
```

---

## Final Verification

- [ ] Run the full backend suite: `cd backend && source venv/bin/activate && python -m pytest -v` — all green.
- [ ] Run the full frontend suite: `cd frontend && CI=true npx react-scripts test` — all green.
- [ ] Rebuild and restart both containers: `docker compose up -d --build backend frontend`.
- [ ] Manually verify in the browser: run an Android review and check the Debug info tab's prompt log shows "as an expert Android code reviewer" in each category's prompt text; confirm the review still completes and scores identically to before (this round only changes wording, not behavior).

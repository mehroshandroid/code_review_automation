# Local Ollama LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing (cosmetic) Azure/Ollama provider toggle actually control which LLM scores a review, adding a real Ollama-backed scoring path alongside Azure, a per-review provider+model selection sent from the browser, and a model picker driven by what's actually installed locally via Ollama.

**Architecture:** Backend: shared prompt/parsing helpers move out of `openai_client.py` into `llm_prompts.py`; a new `ollama_client.py` mirrors `openai_client.py`'s shape against Ollama's OpenAI-compatible endpoint; a thin `llm_client.py` dispatches on a `provider` string; `reviews.py` threads `llm_provider`/`ollama_model` from a new form field through every scoring call; a new `/api/ollama/models` endpoint proxies Ollama's installed-model list. Frontend: `llmProviderStorage.js` gains model persistence and a new "ollama" default; `HomePage` fetches installed models to gate/populate the toggle and dropdown; `AndroidReviewFlow` reads the persisted choice at submit time (re-applying the same empty-models fallback) and sends it with the review.

**Tech Stack:** FastAPI/Python backend (pytest, pytest-asyncio, httpx), React 19 frontend (Jest/React Testing Library, axios). No new dependencies — Ollama's OpenAI-compatible `/v1/chat/completions` endpoint is called via the existing `httpx` client.

## Global Constraints

- Azure OpenAI's behavior, prompts, and rubric are unchanged — Ollama is a second path alongside it, never a replacement.
- `provider` values: only the literal string `"ollama"` routes to Ollama; every other value (including `None`/omitted/unrecognized) routes to Azure — today's only behavior, preserved as the default.
- Ollama config: `OLLAMA_BASE_URL` env var, default `http://host.docker.internal:11434`; `OLLAMA_MODEL` env var, default `qwen2.5-coder:7b`. Both also set explicitly in `docker-compose.yml`'s `backend` service, matching the existing `COMPILER_SERVICE_URL` convention.
- Any Ollama failure (connection refused, timeout, malformed response) falls back to the same shape Azure's client already returns on failure: `{sub_id: {"score": None, "remark": ""}}` for scoring, `""` for general remarks — `_run_review` never needs to know which provider actually ran.
- `test_openai_client.py`'s 15 existing tests must keep passing unmodified after the `llm_prompts.py` extraction — it is the regression baseline for that refactor.
- Follow existing patterns: `httpx.AsyncClient` + monkeypatch-based testing (matching `test_openai_client.py`/`test_compile_checker.py`), never-raise client functions on failure (matching `check_compile_warnings`), the "Industry" design system on the frontend.
- TDD throughout: write the failing test, run it and confirm the failure, implement, run again and confirm the pass, then commit.

---

## Task 1: Extract shared prompt/parsing logic into `llm_prompts.py`

**Files:**
- Create: `backend/app/analyzer/llm_prompts.py`
- Modify: `backend/app/analyzer/openai_client.py` (full rewrite — same public behavior, helpers now imported)
- Test: `backend/tests/test_openai_client.py` (unchanged — used as the regression baseline)

**Interfaces:**
- Produces: `category_instructions(category_name, sub_criteria, descriptions) -> str`, `code_context_message(code_snippets) -> str`, `general_remarks_prompt() -> str`, `build_findings_summary(category_results) -> str`, `normalize_score_result(parsed, sub_criteria) -> dict`, `strip_markdown_fences(content) -> str` — all pure, provider-agnostic. Task 2's `ollama_client.py` imports the same six functions.

This is a behavior-preserving refactor, not a new feature — the "test" is the existing suite staying green throughout.

- [ ] **Step 1: Run the existing suite as a baseline**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_openai_client.py -v`
Expected: PASS — all 15 tests green, before any change.

- [ ] **Step 2: Create the shared module**

Create `backend/app/analyzer/llm_prompts.py`:

```python
import re


def category_instructions(category_name: str, sub_criteria: list, descriptions: dict) -> str:
    criteria_lines = "\n".join(f"{sub_id}: {descriptions.get(sub_id, '')}" for sub_id in sub_criteria)
    return (
        f"Score the following {category_name} sub-criteria based ONLY on the code above:\n"
        f"{criteria_lines}\n\n"
        "For each sub-criterion, score 0 (fails), 1 (meets it), or null if the "
        "code snippet does not contain enough information to judge that specific sub-criterion "
        "(e.g. it asks about PR comments, commit history, or other context not present in "
        "source code -- do not guess or assume in that case, use null). "
        "Each remark must be specific to its own sub-criterion's exact wording above, not a "
        "general comment about the code as a whole or about a different sub-criterion.\n"
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )


def code_context_message(code_snippets: str) -> str:
    return (
        "You are an expert Android code reviewer. Here is the Android project's "
        f"source code for review:\n\n{code_snippets}"
    )


def general_remarks_prompt() -> str:
    return (
        "You are an expert Android code reviewer. Given per-criterion scores and remarks "
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

- [ ] **Step 3: Update `openai_client.py` to import the shared helpers**

Overwrite `backend/app/analyzer/openai_client.py`:

```python
import asyncio
import json
import os

import httpx

from app.analyzer.llm_prompts import (
    build_findings_summary,
    category_instructions,
    code_context_message,
    general_remarks_prompt,
    normalize_score_result,
    strip_markdown_fences,
)

STUB_PREFIX = "[STUB]"


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")


def _zero_tokens() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0}


def _empty_tokens() -> dict:
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None}


def _extract_usage(response) -> dict:
    if response is None:
        return _empty_tokens()
    usage = response.json().get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": details.get("cached_tokens"),
    }


async def score_category(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str) -> tuple:
    if is_stub_mode():
        return _stub_score(category_name, sub_criteria, descriptions)
    return await _live_score(category_name, sub_criteria, descriptions, code_snippets)


async def generate_general_remarks(category_results: dict) -> tuple:
    if is_stub_mode():
        return _stub_general_remarks()
    return await _live_general_remarks(category_results)


def _stub_score(category_name: str, sub_criteria: list, descriptions: dict) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions)
    sub_results = {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _zero_tokens()}
    return sub_results, prompt_info


def _stub_general_remarks() -> tuple:
    text = f"{STUB_PREFIX} No Azure OpenAI key configured; general remarks not generated."
    prompt_info = {"label": "General remarks", "prompt_text": general_remarks_prompt(), "tokens": _zero_tokens()}
    return text, prompt_info


async def _post_with_retry(payload: dict):
    api_base = os.environ["OPENAI_API_BASE"].rstrip("/")
    deployment = os.environ["OPENAI_DEPLOYMENT_NAME"]
    api_version = os.environ["OPENAI_API_VERSION"]
    url = f"{api_base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    headers = {"api-key": os.environ["AZURE_OPENAI_KEY"], "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = None
        for attempt in range(3):
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            break
        if response is None or response.status_code == 429:
            return None
        response.raise_for_status()
        return response


async def _live_score(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions)
    payload = {
        "messages": [
            {"role": "system", "content": code_context_message(code_snippets)},
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


async def _live_general_remarks(category_results: dict) -> tuple:
    system_prompt = general_remarks_prompt()
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

- [ ] **Step 4: Run the suite again to confirm nothing broke**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_openai_client.py -v`
Expected: PASS — all 15 tests still green, byte-for-byte same behavior as Step 1.

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/llm_prompts.py backend/app/analyzer/openai_client.py
git commit -m "refactor: extract shared LLM prompt/parsing helpers into llm_prompts.py"
```

---

## Task 2: `ollama_client.py`

**Files:**
- Create: `backend/app/analyzer/ollama_client.py`
- Test: `backend/tests/test_ollama_client.py`
- Modify: `docker-compose.yml` (env vars for the `backend` service)

**Interfaces:**
- Consumes: `category_instructions`, `code_context_message`, `general_remarks_prompt`, `build_findings_summary`, `normalize_score_result`, `strip_markdown_fences` (Task 1's `llm_prompts.py`).
- Produces: `score_category(category_name, sub_criteria, descriptions, code_snippets, model=None) -> tuple`, `generate_general_remarks(category_results, model=None) -> tuple`, `list_models() -> list[str]`. Task 3's `llm_client.py` calls all three.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_ollama_client.py`:

```python
import httpx
import pytest

from app.analyzer import ollama_client


@pytest.mark.asyncio
async def test_score_category_calls_ollama_endpoint_and_parses_response(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["url"] = url
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "Well named"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await ollama_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}
    assert captured["url"] == "http://fake-ollama:11434/v1/chat/completions"
    assert captured["json"]["model"] == "qwen2.5-coder:7b"
    assert prompt_info["tokens"] == {
        "prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320, "cached_tokens": None,
    }


@pytest.mark.asyncio
async def test_score_category_uses_the_model_override_when_provided(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "ok"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await ollama_client.score_category("Code Structure", ["1.1"], {}, "code here", model="mistral:latest")

    assert captured["json"]["model"] == "mistral:latest"


@pytest.mark.asyncio
async def test_score_category_falls_back_on_connection_error(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")

    async def fake_post(self, url, json=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await ollama_client.score_category("Code Structure", ["1.1", "1.2"], {}, "code here")

    assert result == {
        "1.1": {"score": None, "remark": ""},
        "1.2": {"score": None, "remark": ""},
    }
    assert prompt_info["tokens"] == {
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None,
    }


@pytest.mark.asyncio
async def test_score_category_falls_back_on_malformed_response(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")

    async def fake_post(self, url, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"unexpected": "shape"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await ollama_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": None, "remark": ""}}


@pytest.mark.asyncio
async def test_generate_general_remarks_calls_ollama_and_parses_text(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["json"] = json
        content = "Overall code quality is solid."
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    category_results = {"1": {"sub_scores": {"1.1": {"score": 1, "remark": "Good naming"}}}}
    result, prompt_info = await ollama_client.generate_general_remarks(category_results)

    assert result == "Overall code quality is solid."
    assert "1.1: score=1, remark=Good naming" in captured["json"]["messages"][1]["content"]
    assert prompt_info["label"] == "General remarks"


@pytest.mark.asyncio
async def test_generate_general_remarks_returns_empty_string_on_failure(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")

    async def fake_post(self, url, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"unexpected": "shape"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await ollama_client.generate_general_remarks({})
    assert result == ""


@pytest.mark.asyncio
async def test_list_models_returns_installed_model_names(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")

    async def fake_get(self, url):
        request = httpx.Request("GET", url)
        return httpx.Response(
            status_code=200,
            json={"models": [{"name": "mistral:latest"}, {"name": "qwen2.5-coder:7b"}]},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await ollama_client.list_models()

    assert result == ["mistral:latest", "qwen2.5-coder:7b"]


@pytest.mark.asyncio
async def test_list_models_returns_empty_list_when_ollama_is_unreachable(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")

    async def fake_get(self, url):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await ollama_client.list_models()

    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_ollama_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analyzer.ollama_client'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/analyzer/ollama_client.py`:

```python
import json
import os

import httpx

from app.analyzer.llm_prompts import (
    build_findings_summary,
    category_instructions,
    code_context_message,
    general_remarks_prompt,
    normalize_score_result,
    strip_markdown_fences,
)

DEFAULT_OLLAMA_BASE_URL = "http://host.docker.internal:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"
TIMEOUT_SECONDS = 120.0


def _base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def _model(model: str | None) -> str:
    return model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


def _empty_tokens() -> dict:
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None}


def _extract_usage(response) -> dict:
    if response is None:
        return _empty_tokens()
    usage = response.json().get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": None,
    }


async def _post(payload: dict):
    url = f"{_base_url()}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response
    except (httpx.HTTPError, OSError):
        return None


async def score_category(
    category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, model: str | None = None
) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions)
    payload = {
        "model": _model(model),
        "messages": [
            {"role": "system", "content": code_context_message(code_snippets)},
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


async def generate_general_remarks(category_results: dict, model: str | None = None) -> tuple:
    system_prompt = general_remarks_prompt()
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


async def list_models() -> list:
    url = f"{_base_url()}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return [model["name"] for model in response.json().get("models", [])]
    except (httpx.HTTPError, OSError, KeyError, TypeError):
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_ollama_client.py -v`
Expected: PASS — all 8 tests green.

- [ ] **Step 5: Add the docker-compose env vars**

In `docker-compose.yml`, add to the `backend` service's `environment` list (alongside the existing `COMPILER_SERVICE_URL` line):

```yaml
      - COMPILER_SERVICE_URL=http://compiler:8000
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - OLLAMA_MODEL=qwen2.5-coder:7b
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/analyzer/ollama_client.py backend/tests/test_ollama_client.py docker-compose.yml
git commit -m "feat: add ollama_client.py for local LLM scoring and model listing"
```

---

## Task 3: Provider dispatcher — `llm_client.py`

**Files:**
- Create: `backend/app/analyzer/llm_client.py`
- Test: `backend/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `openai_client.score_category`/`generate_general_remarks` (Task 1, unchanged signatures); `ollama_client.score_category`/`generate_general_remarks` (Task 2).
- Produces: `score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None) -> tuple`, `generate_general_remarks(provider, category_results, model=None) -> tuple`. Task 4's `reviews.py` imports these two names in place of `openai_client`'s.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_llm_client.py`:

```python
import pytest

from app.analyzer import llm_client


@pytest.mark.asyncio
async def test_score_category_routes_to_ollama_when_provider_is_ollama(monkeypatch):
    captured = {}

    async def fake_ollama_score_category(category_name, sub_criteria, descriptions, code_snippets, model=None):
        captured["args"] = (category_name, sub_criteria, descriptions, code_snippets, model)
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "score_category", fake_ollama_score_category)

    result, _ = await llm_client.score_category("ollama", "Code Structure", ["1.1"], {}, "code", model="mistral:latest")

    assert result == {"1.1": {"score": 1, "remark": "ok"}}
    assert captured["args"] == ("Code Structure", ["1.1"], {}, "code", "mistral:latest")


@pytest.mark.asyncio
async def test_score_category_routes_to_openai_for_any_non_ollama_provider(monkeypatch):
    calls = []

    async def fake_openai_score_category(category_name, sub_criteria, descriptions, code_snippets):
        calls.append(category_name)
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.openai_client, "score_category", fake_openai_score_category)

    await llm_client.score_category("azure", "Code Structure", ["1.1"], {}, "code")
    await llm_client.score_category(None, "Code Structure", ["1.1"], {}, "code")
    await llm_client.score_category("something-unrecognized", "Code Structure", ["1.1"], {}, "code")

    assert calls == ["Code Structure", "Code Structure", "Code Structure"]


@pytest.mark.asyncio
async def test_generate_general_remarks_routes_to_ollama_when_provider_is_ollama(monkeypatch):
    captured = {}

    async def fake_ollama_general_remarks(category_results, model=None):
        captured["args"] = (category_results, model)
        return "ollama summary", {"label": "General remarks", "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "generate_general_remarks", fake_ollama_general_remarks)

    result, _ = await llm_client.generate_general_remarks("ollama", {"1": {}}, model="mistral:latest")

    assert result == "ollama summary"
    assert captured["args"] == ({"1": {}}, "mistral:latest")


@pytest.mark.asyncio
async def test_generate_general_remarks_routes_to_openai_by_default(monkeypatch):
    async def fake_openai_general_remarks(category_results):
        return "azure summary", {"label": "General remarks", "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.openai_client, "generate_general_remarks", fake_openai_general_remarks)

    result, _ = await llm_client.generate_general_remarks("azure", {"1": {}})

    assert result == "azure summary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analyzer.llm_client'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/analyzer/llm_client.py`:

```python
from app.analyzer import ollama_client, openai_client


async def score_category(
    provider: str, category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, model: str | None = None
) -> tuple:
    if provider == "ollama":
        return await ollama_client.score_category(category_name, sub_criteria, descriptions, code_snippets, model=model)
    return await openai_client.score_category(category_name, sub_criteria, descriptions, code_snippets)


async def generate_general_remarks(provider: str, category_results: dict, model: str | None = None) -> tuple:
    if provider == "ollama":
        return await ollama_client.generate_general_remarks(category_results, model=model)
    return await openai_client.generate_general_remarks(category_results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_llm_client.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/llm_client.py backend/tests/test_llm_client.py
git commit -m "feat: add llm_client.py provider dispatcher"
```

---

## Task 4: Wire `llm_client` into `reviews.py`

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/tests/test_reviews_create.py` (update 3 existing fake `score_category` functions to the new signature; add one new test)
- Modify: `backend/tests/test_reviews_integration.py` (update `_capturing_score_category`'s signature)

**Interfaces:**
- Consumes: `llm_client.score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None)`, `llm_client.generate_general_remarks(provider, category_results, model=None)` (Task 3).
- Produces: `POST /api/reviews` accepts `llmProvider` (form field, default `"azure"`) and `ollamaModel` (form field, default `None`); `_run_review` gains `llm_provider`/`ollama_model` parameters (both with defaults, so every existing call site that omits them keeps behaving exactly as before).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_reviews_create.py` (a new test, placed after `test_run_review_updates_category_scores_progressively`):

```python
async def test_run_review_passes_llm_provider_and_model_through_to_scoring_calls(monkeypatch):
    review_id = "llm-provider-threading-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_providers = []
    captured_models = []

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None):
        captured_providers.append(provider)
        captured_models.append(model)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_generate_general_remarks(provider, category_results, model=None):
        captured_providers.append(provider)
        captured_models.append(model)
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
        llm_provider="ollama", ollama_model="qwen2.5-coder:7b",
    )

    # 5 category calls + 1 general-remarks call, all carrying the same provider/model.
    assert captured_providers == ["ollama"] * 6
    assert captured_models == ["qwen2.5-coder:7b"] * 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py::test_run_review_passes_llm_provider_and_model_through_to_scoring_calls -v`
Expected: FAIL — `TypeError: _run_review() got an unexpected keyword argument 'llm_provider'`.

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, change the import:

```python
from app.analyzer.llm_client import generate_general_remarks, score_category
```

(replacing the current `from app.analyzer.openai_client import generate_general_remarks, score_category`).

Add `Form` to the FastAPI import:

```python
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
```

Change `create_review`'s signature and body:

```python
@router.post("/api/reviews")
async def create_review(
    androidZip: UploadFile = File(...),
    excelTemplate: UploadFile = File(...),
    llmProvider: str = Form("azure"),
    ollamaModel: str | None = Form(None),
):
    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"

    try:
        zip_path.write_bytes(await androidZip.read())
        template_path.write_bytes(await excelTemplate.read())
    except Exception as exc:
        logger.exception("Review %s failed while saving uploads", review_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        state = _new_review_state()
        state["status"] = "error"
        state["phase"] = "error"
        state["message"] = "Review failed"
        state["error"] = f"Failed to save uploaded files: {exc}"
        _reviews[review_id] = state
        return {"review_id": review_id, "status": "error"}

    zip_valid = (androidZip.filename or "").endswith(".zip")
    template_valid = (excelTemplate.filename or "").endswith(".xlsx")
    project_name = Path(androidZip.filename).stem if androidZip.filename else "Unknown Project"

    state = _new_review_state()
    state["project_name"] = project_name
    _reviews[review_id] = state
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel,
        )
    )
    return {"review_id": review_id, "status": "processing"}
```

Change `_run_review`'s signature (add two trailing parameters with defaults):

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
) -> None:
```

Update the scoring-loop call site:

```python
            sub_results, prompt_info = await score_category(
                llm_provider, category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context,
                model=ollama_model,
            )
```

Update the general-remarks call site:

```python
        general_remarks, remarks_prompt_info = await generate_general_remarks(
            llm_provider, scores_by_category, model=ollama_model
        )
```

Now update the three existing tests in `backend/tests/test_reviews_create.py` whose fake `score_category` functions no longer match the call site's new signature (each currently reads `async def ...(category_name, sub_criteria, descriptions, code_snippets):` — add a leading `provider` parameter and a trailing `model=None` keyword parameter to each, ignoring both in the body):

In `test_run_review_updates_message_per_category_during_scoring`:

```python
    async def _recording_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None):
        seen_messages.append(_reviews[review_id]["message"])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info
```

In `test_run_review_updates_category_scores_progressively`:

```python
    async def _recording_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None):
        snapshots.append([(e["id"], e["percent_points"]) for e in _reviews[review_id]["category_scores"]])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info
```

In `test_run_review_scores_1_4_from_compile_check_and_excludes_it_from_the_llm`:

```python
    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info
```

In `backend/tests/test_reviews_integration.py`, update `_capturing_score_category`:

```python
    real_score_category = reviews_module.score_category
    captured_code_snippets = []

    async def _capturing_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None):
        captured_code_snippets.append(code_snippets)
        return await real_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=model)

    monkeypatch.setattr(reviews_module, "score_category", _capturing_score_category)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py tests/test_reviews_integration.py -v`
Expected: PASS — all tests in both files green, including the new threading test and the three updated fakes.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: PASS — full backend suite green (existing suite + Tasks 1-4's new tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_integration.py
git commit -m "feat: thread llmProvider/ollamaModel from the review request through every scoring call"
```

---

## Task 5: New `/api/ollama/models` endpoint

**Files:**
- Create: `backend/app/api/ollama.py`
- Modify: `backend/main.py` (register the new router)
- Test: `backend/tests/test_ollama_models_endpoint.py`

**Interfaces:**
- Consumes: `ollama_client.list_models()` (Task 2).
- Produces: `GET /api/ollama/models` → `{"models": [...]}`, always `200`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_ollama_models_endpoint.py`:

```python
from fastapi.testclient import TestClient

import app.api.ollama as ollama_api
from main import app

client = TestClient(app)


def test_list_ollama_models_returns_installed_models(monkeypatch):
    async def fake_list_models():
        return ["mistral:latest", "qwen2.5-coder:7b"]

    monkeypatch.setattr(ollama_api.ollama_client, "list_models", fake_list_models)

    response = client.get("/api/ollama/models")

    assert response.status_code == 200
    assert response.json() == {"models": ["mistral:latest", "qwen2.5-coder:7b"]}


def test_list_ollama_models_returns_empty_list_when_unreachable(monkeypatch):
    async def fake_list_models():
        return []

    monkeypatch.setattr(ollama_api.ollama_client, "list_models", fake_list_models)

    response = client.get("/api/ollama/models")

    assert response.status_code == 200
    assert response.json() == {"models": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_ollama_models_endpoint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.ollama'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/api/ollama.py`:

```python
from fastapi import APIRouter

from app.analyzer import ollama_client

router = APIRouter()


@router.get("/api/ollama/models")
async def list_ollama_models():
    return {"models": await ollama_client.list_models()}
```

In `backend/main.py`, add the import and registration:

```python
from app.api.ollama import router as ollama_router
```

```python
app.include_router(reviews_router)
app.include_router(ollama_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_ollama_models_endpoint.py -v`
Expected: PASS — both tests green.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: PASS — full backend suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/ollama.py backend/main.py backend/tests/test_ollama_models_endpoint.py
git commit -m "feat: add GET /api/ollama/models endpoint"
```

---

## Task 6: Frontend — `llmProviderStorage.js` model persistence + new default

**Files:**
- Modify: `frontend/src/services/llmProviderStorage.js`
- Modify: `frontend/src/services/llmProviderStorage.test.jsx` (full rewrite)

**Interfaces:**
- Produces: `getOllamaModel(): string | null`, `setOllamaModel(model: string): void` (new); `getLlmProvider()`'s no-value-stored default changes from `"azure"` to `"ollama"`.

- [ ] **Step 1: Write the failing tests**

Overwrite `frontend/src/services/llmProviderStorage.test.jsx`:

```jsx
import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel } from "./llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

test("defaults to ollama when nothing is stored", () => {
  expect(getLlmProvider()).toBe("ollama");
});

test("returns a previously-stored value", () => {
  localStorage.setItem("llmProvider", "azure");
  expect(getLlmProvider()).toBe("azure");
});

test("setLlmProvider writes to localStorage under the expected key", () => {
  setLlmProvider("azure");
  expect(localStorage.getItem("llmProvider")).toBe("azure");
  expect(getLlmProvider()).toBe("azure");
});

test("getOllamaModel returns null when nothing is stored", () => {
  expect(getOllamaModel()).toBeNull();
});

test("setOllamaModel writes to localStorage under the expected key", () => {
  setOllamaModel("qwen2.5-coder:7b");
  expect(localStorage.getItem("ollamaModel")).toBe("qwen2.5-coder:7b");
  expect(getOllamaModel()).toBe("qwen2.5-coder:7b");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/services/llmProviderStorage.test.jsx`
Expected: FAIL — `getLlmProvider()` still returns `"azure"` by default, and `getOllamaModel`/`setOllamaModel` don't exist yet.

- [ ] **Step 3: Implement**

Overwrite `frontend/src/services/llmProviderStorage.js`:

```js
const STORAGE_KEY = "llmProvider";
const DEFAULT_PROVIDER = "ollama";
const MODEL_STORAGE_KEY = "ollamaModel";

export function getLlmProvider() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_PROVIDER;
}

export function setLlmProvider(provider) {
  localStorage.setItem(STORAGE_KEY, provider);
}

export function getOllamaModel() {
  return localStorage.getItem(MODEL_STORAGE_KEY) || null;
}

export function setOllamaModel(model) {
  localStorage.setItem(MODEL_STORAGE_KEY, model);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/services/llmProviderStorage.test.jsx`
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/llmProviderStorage.js frontend/src/services/llmProviderStorage.test.jsx
git commit -m "feat: persist Ollama model choice; default provider is now ollama"
```

---

## Task 7: Frontend — `services/api.js` gains `getOllamaModels` + provider/model on `createReview`

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/services/api.test.js`

**Interfaces:**
- Produces: `getOllamaModels(): Promise<string[]>`; `createReview(androidZip, excelTemplate, llmProvider, ollamaModel)` — the last two parameters are new and optional (omitted fields are simply not sent).

- [ ] **Step 1: Write the failing tests**

Overwrite `frontend/src/services/api.test.js`:

```js
import axios from "axios";
import { createReview, getProgress, getDownloadUrl, getOllamaModels } from "./api";

jest.mock("axios");

describe("createReview", () => {
  it("posts multipart form data with both files and returns the response body", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    const result = await createReview(zip, xlsx);

    expect(result).toEqual({ review_id: "abc-123", status: "processing" });
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, formData] = axios.post.mock.calls[0];
    expect(url).toContain("/reviews");
    expect(formData.get("androidZip")).toBe(zip);
    expect(formData.get("excelTemplate")).toBe(xlsx);
  });

  it("includes llmProvider and ollamaModel fields when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "ollama", "qwen2.5-coder:7b");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("llmProvider")).toBe("ollama");
    expect(formData.get("ollamaModel")).toBe("qwen2.5-coder:7b");
  });

  it("omits llmProvider and ollamaModel fields when not provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx);

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("llmProvider")).toBeNull();
    expect(formData.get("ollamaModel")).toBeNull();
  });
});

describe("getProgress", () => {
  it("fetches progress for a review id and returns the response body", async () => {
    const progressBody = {
      status: "processing", phase: "scoring", progress: 60, message: "Scoring",
      stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    };
    axios.get.mockResolvedValue({ data: progressBody });

    const result = await getProgress("abc-123");

    expect(result).toEqual(progressBody);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/reviews/abc-123/progress"));
  });
});

describe("getOllamaModels", () => {
  it("fetches installed Ollama models and returns the list", async () => {
    axios.get.mockResolvedValue({ data: { models: ["mistral:latest", "qwen2.5-coder:7b"] } });

    const result = await getOllamaModels();

    expect(result).toEqual(["mistral:latest", "qwen2.5-coder:7b"]);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/ollama/models"));
  });
});

describe("getDownloadUrl", () => {
  it("combines the API origin with the backend's returned download path without doubling /api", () => {
    const url = getDownloadUrl("/api/reviews/abc-123/download");
    expect(url).toBe("http://localhost:8000/api/reviews/abc-123/download");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js`
Expected: FAIL — `getOllamaModels` is not exported yet, and the new `createReview` field assertions fail (no `llmProvider`/`ollamaModel` sent).

- [ ] **Step 3: Implement**

Overwrite `frontend/src/services/api.js`:

```js
import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, "");

export async function createReview(androidZip, excelTemplate, llmProvider, ollamaModel) {
  const formData = new FormData();
  formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}

export async function getProgress(reviewId) {
  const response = await axios.get(`${API_BASE_URL}/reviews/${reviewId}/progress`);
  return response.data;
}

export async function getOllamaModels() {
  const response = await axios.get(`${API_BASE_URL}/ollama/models`);
  return response.data.models;
}

export function getDownloadUrl(downloadPath) {
  return `${API_ORIGIN}${downloadPath}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/services/api.test.js`
Expected: PASS — all 6 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js
git commit -m "feat: add getOllamaModels and thread provider/model through createReview"
```

---

## Task 8: Frontend — `HomePage` model dropdown + gating

**Files:**
- Modify: `frontend/src/pages/HomePage.jsx`
- Modify: `frontend/src/pages/HomePage.test.jsx` (full rewrite)

**Interfaces:**
- Consumes: `getOllamaModels()` (Task 7); `getLlmProvider`/`setLlmProvider`/`getOllamaModel`/`setOllamaModel` (Task 6).
- Produces: no new exports — same `HomePage` default export, no props, as before.

- [ ] **Step 1: Write the failing tests**

Overwrite `frontend/src/pages/HomePage.test.jsx`:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import HomePage from "./HomePage";
import { getLlmProvider, getOllamaModel } from "../services/llmProviderStorage";
import { getOllamaModels } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getOllamaModels: jest.fn(),
}));

beforeEach(() => {
  localStorage.clear();
  jest.resetAllMocks();
});

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

test("renders a link for each platform pointing at /review/<id>", async () => {
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  renderHome();
  expect(screen.getByRole("link", { name: /android/i })).toHaveAttribute("href", "/review/android");
  expect(screen.getByRole("link", { name: /ios/i })).toHaveAttribute("href", "/review/ios");
  expect(screen.getByRole("link", { name: /\.net/i })).toHaveAttribute("href", "/review/dotnet");
  expect(screen.getByRole("link", { name: /web \(react\)/i })).toHaveAttribute("href", "/review/web");
});

test("defaults to Ollama highlighted when models are available", async () => {
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  renderHome();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).not.toHaveClass("btn-primary");
});

test("clicking Azure OpenAI persists the choice and updates the highlighted button", async () => {
  const user = userEvent.setup();
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  renderHome();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary"));

  await user.click(screen.getByRole("button", { name: "Azure OpenAI" }));

  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary");
  expect(getLlmProvider()).toBe("azure");
});

test("shows a model dropdown populated from installed models, defaulting to the first one", async () => {
  getOllamaModels.mockResolvedValue(["mistral:latest", "qwen2.5-coder:7b"]);
  renderHome();

  const select = await screen.findByLabelText("Ollama model");
  expect(select.value).toBe("mistral:latest");
  expect(screen.getByRole("option", { name: "qwen2.5-coder:7b" })).toBeInTheDocument();
});

test("selecting a model persists it to localStorage", async () => {
  const user = userEvent.setup();
  getOllamaModels.mockResolvedValue(["mistral:latest", "qwen2.5-coder:7b"]);
  renderHome();

  const select = await screen.findByLabelText("Ollama model");
  await user.selectOptions(select, "qwen2.5-coder:7b");

  expect(getOllamaModel()).toBe("qwen2.5-coder:7b");
});

test("disables Ollama and forces Azure when no local models are installed", async () => {
  getOllamaModels.mockResolvedValue([]);
  renderHome();

  await waitFor(() => expect(screen.getByRole("button", { name: "Ollama (local)" })).toBeDisabled());
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary");
  expect(screen.queryByLabelText("Ollama model")).not.toBeInTheDocument();
  // Forcing the effective provider does not overwrite the stored preference.
  expect(getLlmProvider()).toBe("ollama");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/pages/HomePage.test.jsx`
Expected: FAIL — the toggle still defaults to whatever `getLlmProvider()` currently returns without regard to fetched models, there is no model dropdown, and the Ollama button is never disabled.

- [ ] **Step 3: Implement**

Overwrite `frontend/src/pages/HomePage.jsx`:

```jsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import CornerMarks from "../components/CornerMarks";
import { PLATFORMS } from "../platforms";
import { getOllamaModels } from "../services/api";
import { getLlmProvider, setLlmProvider, getOllamaModel, setOllamaModel } from "../services/llmProviderStorage";

const LLM_PROVIDERS = [
  { id: "azure", label: "Azure OpenAI" },
  { id: "ollama", label: "Ollama (local)" },
];

export default function HomePage() {
  const [llmProvider, setLlmProviderState] = useState(() => getLlmProvider());
  const [ollamaModel, setOllamaModelState] = useState(() => getOllamaModel());
  const [ollamaModels, setOllamaModels] = useState(null); // null = still loading

  useEffect(() => {
    let cancelled = false;
    getOllamaModels()
      .then((models) => { if (!cancelled) setOllamaModels(models); })
      .catch(() => { if (!cancelled) setOllamaModels([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!ollamaModels || ollamaModels.length === 0) return;
    const initial = ollamaModels.includes(ollamaModel) ? ollamaModel : ollamaModels[0];
    if (initial !== ollamaModel) {
      setOllamaModel(initial);
      setOllamaModelState(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ollamaModels]);

  function handleSelectProvider(providerId) {
    setLlmProvider(providerId);
    setLlmProviderState(providerId);
  }

  function handleSelectModel(model) {
    setOllamaModel(model);
    setOllamaModelState(model);
  }

  const ollamaEnabled = ollamaModels === null || ollamaModels.length > 0;
  const effectiveProvider = !ollamaEnabled && llmProvider === "ollama" ? "azure" : llmProvider;

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav"><span className="nav-brand">Code Review Automation</span></nav>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            Code Review Automation
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Choose a platform to start a review.
          </p>
        </header>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
          {PLATFORMS.map((platform) => (
            <Link
              key={platform.id}
              to={`/review/${platform.id}`}
              className="card blueprint elev-md"
              style={{ padding: "var(--space-6)", textDecoration: "none", color: "inherit" }}
            >
              <CornerMarks />
              <div className="card-kicker">{platform.available ? "Available" : "Coming soon"}</div>
              <div className="card-title" style={{ fontSize: 20 }}>{platform.label}</div>
            </Link>
          ))}
        </div>

        <div className="card blueprint" style={{ padding: "var(--space-6)", marginTop: "var(--space-6)" }}>
          <CornerMarks />
          <div className="card-kicker">LLM provider</div>
          <div className="card-title" style={{ fontSize: 20 }}>Choose a model provider</div>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
            {LLM_PROVIDERS.map((provider) => {
              const disabled = provider.id === "ollama" && !ollamaEnabled;
              return (
                <button
                  key={provider.id}
                  type="button"
                  className={`btn ${effectiveProvider === provider.id ? "btn-primary" : ""}`}
                  disabled={disabled}
                  onClick={() => handleSelectProvider(provider.id)}
                >
                  {provider.label}
                </button>
              );
            })}
          </div>
          {effectiveProvider === "ollama" && ollamaModels && ollamaModels.length > 0 && (
            <select
              aria-label="Ollama model"
              value={ollamaModel || ollamaModels[0]}
              onChange={(event) => handleSelectModel(event.target.value)}
              className="input"
              style={{ marginTop: "var(--space-3)" }}
            >
              {ollamaModels.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
          )}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/HomePage.test.jsx`
Expected: PASS — all 6 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/HomePage.jsx frontend/src/pages/HomePage.test.jsx
git commit -m "feat: gate and populate the Ollama toggle from installed models"
```

---

## Task 9: Frontend — `AndroidReviewFlow` sends provider + model at submit time

**Files:**
- Modify: `frontend/src/pages/AndroidReviewFlow.jsx`
- Modify: `frontend/src/pages/AndroidReviewFlow.test.jsx`

**Interfaces:**
- Consumes: `getOllamaModels()` (Task 7); `getLlmProvider`/`getOllamaModel` (Task 6); `createReview(androidZip, excelTemplate, llmProvider, ollamaModel)` (Task 7).
- Produces: no new exports — same `AndroidReviewFlow` default export, no props, as before.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/pages/AndroidReviewFlow.test.jsx`, update the import and mock block:

```jsx
import { createReview, getProgress, getOllamaModels } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
  getOllamaModels: jest.fn(),
}));
```

Update `beforeEach` to establish a deterministic Azure baseline for all the existing tests (none of which are about provider selection):

```jsx
beforeEach(() => {
  jest.useFakeTimers();
  localStorage.clear();
  localStorage.setItem("llmProvider", "azure");
  getOllamaModels.mockResolvedValue([]);
});
```

Then add two new tests at the end of the file:

```jsx
test("sends the selected Ollama provider and model when available", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  localStorage.setItem("llmProvider", "ollama");
  localStorage.setItem("ollamaModel", "qwen2.5-coder:7b");
  getOllamaModels.mockResolvedValue(["qwen2.5-coder:7b"]);
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "ollama", "qwen2.5-coder:7b");
});

test("falls back to Azure when Ollama is selected but no models are installed", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  localStorage.setItem("llmProvider", "ollama");
  getOllamaModels.mockResolvedValue([]);
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    total_score_pct: null, project_name: null, category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(createReview).toHaveBeenCalledWith(expect.anything(), expect.anything(), "azure", null);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx`
Expected: FAIL — `createReview` is currently called with only two arguments (`androidZip`, `excelTemplate`); the two new tests' `toHaveBeenCalledWith` assertions fail.

- [ ] **Step 3: Implement**

In `frontend/src/pages/AndroidReviewFlow.jsx`, update the imports:

```jsx
import { createReview, getOllamaModels } from "../services/api";
import { getLlmProvider, getOllamaModel } from "../services/llmProviderStorage";
```

Replace `handleUpload`:

```jsx
  const handleUpload = useCallback(async (androidZip, excelTemplate) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const models = await getOllamaModels().catch(() => []);
      const storedProvider = getLlmProvider();
      const effectiveProvider = storedProvider === "ollama" && models.length === 0 ? "azure" : storedProvider;
      const effectiveModel = effectiveProvider === "ollama" ? getOllamaModel() : null;

      const result = await createReview(androidZip, excelTemplate, effectiveProvider, effectiveModel);
      if (result.status === "error") {
        setErrorMessage(result.error || "Upload failed");
        setState("error");
        return;
      }
      setReviewId(result.review_id);
      setState("polling");
    } catch (err) {
      setErrorMessage("Failed to start review. Is the server running?");
      setState("error");
    }
  }, []);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx`
Expected: PASS — all tests green, including the two new ones.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && CI=true npx react-scripts test`
Expected: PASS — full frontend suite green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AndroidReviewFlow.jsx frontend/src/pages/AndroidReviewFlow.test.jsx
git commit -m "feat: send the selected LLM provider and model when starting a review"
```

---

## Final Verification

- [ ] Run the full backend suite: `cd backend && source venv/bin/activate && python -m pytest -v` — all green.
- [ ] Run the full frontend suite: `cd frontend && CI=true npx react-scripts test` — all green.
- [ ] Rebuild and restart both containers: `docker compose up -d --build backend frontend`.
- [ ] Pull the recommended model if not already present: `ollama pull qwen2.5-coder:7b`.
- [ ] Manually verify in the browser: the landing page's Ollama toggle is enabled and highlighted by default (models exist), with a working model dropdown; running an Android review with Ollama selected actually calls the local model (check backend container logs for a request to `host.docker.internal:11434`); switching back to Azure and running a review still works exactly as before; temporarily stopping the local `ollama serve` process and reloading the landing page shows Ollama disabled with Azure auto-selected.

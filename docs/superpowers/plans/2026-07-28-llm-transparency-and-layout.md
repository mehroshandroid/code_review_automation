# LLM Transparency & Layout Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture and expose per-LLM-call token usage and the exact prompt text sent, reorder category-scoring messages so Azure's automatic prompt caching can discount the repeated code context, and rework the page into a 2-band layout (upload/progress + graph/stats on top, a scrollable prompt debug log below).

**Architecture:** `openai_client.py`'s `score_category`/`generate_general_remarks` change from returning a bare result to `(result, prompt_info)` tuples; `reviews.py` accumulates these into `state["prompt_log"]` (live-appended, same pattern as `category_scores`) and stores the shared `code_context` once; both are exposed on `/progress`. The frontend gets two new components (`LlmUsageStats`, `PromptDebugLog`), `StatsDisplay` sheds its nested chart/findings (now rendered once in the shared layout instead of duplicated), and `App.jsx`'s running/completed states become a 2-column top band + full-width bottom band.

**Tech Stack:** Same as before — FastAPI/Python backend, React 19 frontend, Recharts (already added).

## Global Constraints

- No combining of the 5 category-scoring calls into one request — keep 5 separate calls so the live per-category bar fill-in is preserved.
- The code-context/instructions message reorder applies **only** to category-scoring calls; the general-remarks call is unchanged.
- `prompt_text` in every `prompt_info` entry is always the category-specific rubric/instructions text (the part that varies), never the shared code blob, regardless of which message role it's actually sent under.
- Stub mode (no `AZURE_OPENAI_KEY`) still builds and returns real `prompt_text`; `tokens` are all `0` in stub mode, all `None` when a live call fails to get a response.
- Idle and error screens are unchanged (920px column). Only polling/completed screens widen and switch to the 2-band layout.
- The right column (chart + `LlmUsageStats`) and the bottom band (`PromptDebugLog`) share one gating condition: `phase` is `"scoring"`, `"generating"`, or `"completed"`.

---

### Task 1: Backend — reorder prompts for caching, capture tokens, change return shape

**Files:**
- Modify: `backend/app/analyzer/openai_client.py` (full rewrite)
- Test: `backend/tests/test_openai_client.py` (full rewrite)

**Interfaces:**
- Produces: `score_category(category_name, sub_criteria, descriptions, code_snippets) -> (dict, dict)` and `generate_general_remarks(category_results) -> (str, dict)` — the second element of each tuple is `prompt_info = {"label": str, "prompt_text": str, "tokens": {"prompt_tokens": int|None, "completion_tokens": int|None, "total_tokens": int|None, "cached_tokens": int|None}}`. This is a breaking change to both functions' return shape — every caller (Task 2) and every existing test in this file is updated together.

- [ ] **Step 1: Write the failing tests**

Replace `backend/tests/test_openai_client.py` entirely:

```python
import httpx
import pytest

from app.analyzer import openai_client


@pytest.mark.asyncio
async def test_stub_mode_returns_placeholder_scores(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    result, prompt_info = await openai_client.score_category("Code Structure", ["1.1", "1.2"], {}, "code here")
    assert set(result.keys()) == {"1.1", "1.2"}
    for sub in result.values():
        assert sub["score"] == 1
        assert sub["remark"].startswith("[STUB]")
    assert prompt_info["label"] == "Code Structure"
    assert "Code Structure" in prompt_info["prompt_text"]
    assert prompt_info["tokens"] == {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
    }


@pytest.mark.asyncio
async def test_live_mode_calls_azure_endpoint_and_parses_response(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        content = '{"1.1": {"score": 1, "remark": "Well named"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await openai_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}
    assert captured["headers"]["api-key"] == "test-key"
    assert "gpt-4o-mini" in captured["url"]
    assert captured["json"]["temperature"] == 0.3
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert prompt_info["tokens"] == {
        "prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540, "cached_tokens": None,
    }


@pytest.mark.asyncio
async def test_live_mode_sends_code_as_the_first_message_for_prompt_caching(monkeypatch):
    # The code is identical across all 5 category calls; putting it first (as
    # a stable message-list prefix) lets Azure's automatic prompt caching
    # discount the repeated tokens. The category-specific rubric, which
    # varies per call, comes second.
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

    await openai_client.score_category("Code Structure", ["1.1"], {}, "class MainActivity {}")

    assert "class MainActivity {}" in captured["json"]["messages"][0]["content"]
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_live_mode_grounds_the_prompt_with_real_descriptions(monkeypatch):
    # Root cause of the reported "remark unrelated to its clause" bug: the
    # prompt previously only sent bare ids like "2.4", never their actual
    # meaning, so the model had to guess what each id was asking about.
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        content = '{"2.4": {"score": 1, "remark": "ok"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    descriptions = {"2.4": "Keystore information should be stored in env. Or gradle"}
    _, prompt_info = await openai_client.score_category(
        "Reliability, Security & Observability", ["2.4"], descriptions, "code here"
    )

    instructions = captured["json"]["messages"][1]["content"]
    assert "2.4: Keystore information should be stored in env. Or gradle" in instructions
    assert "null" in instructions.lower()
    assert "specific to its own sub-criterion" in instructions
    assert instructions == prompt_info["prompt_text"]


@pytest.mark.asyncio
async def test_live_mode_reorders_result_to_match_requested_sub_criteria(monkeypatch):
    # The model's JSON key order is not guaranteed to match the requested
    # sub_criteria order -- callers rely on dict order to align each score to
    # the correct Excel row positionally, so this must be enforced here.
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        content = '{"1.3": {"score": 0, "remark": "c"}, "1.1": {"score": 1, "remark": "a"}, "1.2": {"score": 0.5, "remark": "b"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await openai_client.score_category("Code Structure", ["1.1", "1.2", "1.3"], {}, "code here")

    assert list(result.keys()) == ["1.1", "1.2", "1.3"]
    assert result == {
        "1.1": {"score": 1, "remark": "a"},
        "1.2": {"score": 0.5, "remark": "b"},
        "1.3": {"score": 0, "remark": "c"},
    }


@pytest.mark.asyncio
async def test_live_mode_fills_in_a_key_the_model_omitted(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        content = '{"1.1": {"score": 1, "remark": "a"}, "1.3": {"score": 0, "remark": "c"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await openai_client.score_category("Code Structure", ["1.1", "1.2", "1.3"], {}, "code here")

    assert list(result.keys()) == ["1.1", "1.2", "1.3"]
    assert result["1.2"] == {"score": None, "remark": ""}


@pytest.mark.asyncio
async def test_live_mode_drops_an_unexpected_extra_key(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        content = '{"1.1": {"score": 1, "remark": "a"}, "1.4": {"score": 0, "remark": "hallucinated"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await openai_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert list(result.keys()) == ["1.1"]


@pytest.mark.asyncio
async def test_live_mode_strips_markdown_fences_if_model_adds_them_anyway(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        content = '```json\n{"1.1": {"score": 1, "remark": "Well named"}}\n```'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await openai_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}


@pytest.mark.asyncio
async def test_live_mode_falls_back_on_malformed_response_envelope(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"unexpected": "shape"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await openai_client.score_category("Code Structure", ["1.1", "1.2"], {}, "code here")

    assert result == {
        "1.1": {"score": None, "remark": ""},
        "1.2": {"score": None, "remark": ""},
    }


@pytest.mark.asyncio
async def test_generate_general_remarks_stub_mode(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    result, prompt_info = await openai_client.generate_general_remarks({})
    assert result.startswith("[STUB]")
    assert prompt_info["label"] == "General remarks"
    assert prompt_info["tokens"] == {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
    }


@pytest.mark.asyncio
async def test_generate_general_remarks_live_mode(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        content = "Overall code quality is solid, with weak exception handling."
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    category_results = {
        "1": {"sub_scores": {"1.1": {"score": 1, "remark": "Good naming"}}},
        "2": {"sub_scores": {"2.1": {"score": 0, "remark": "No exception handling"}}},
    }
    result, prompt_info = await openai_client.generate_general_remarks(category_results)

    assert result == "Overall code quality is solid, with weak exception handling."
    assert "1.1: score=1, remark=Good naming" in captured["json"]["messages"][1]["content"]
    assert "response_format" not in captured["json"]
    assert prompt_info["label"] == "General remarks"
    assert prompt_info["prompt_text"] == captured["json"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_generate_general_remarks_returns_empty_string_on_failure(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"unexpected": "shape"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await openai_client.generate_general_remarks({})
    assert result == ""


@pytest.mark.asyncio
async def test_live_mode_returns_fallback_after_retry_exhaustion_on_429(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    call_count = {"n": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["n"] += 1
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=429, json={"error": "rate limited"}, request=request)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(openai_client.asyncio, "sleep", fake_sleep)

    result, prompt_info = await openai_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": None, "remark": ""}}
    assert call_count["n"] == 3
    assert prompt_info["tokens"] == {
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_openai_client.py -v`
Expected: FAIL — `score_category`/`generate_general_remarks` still return bare results, not tuples, so unpacking (`result, prompt_info = ...`) raises `TypeError: cannot unpack non-iterable dict/str`.

- [ ] **Step 3: Implement the rewrite**

Replace `backend/app/analyzer/openai_client.py` entirely:

```python
import asyncio
import json
import os
import re

import httpx

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


def _category_instructions(category_name: str, sub_criteria: list, descriptions: dict) -> str:
    criteria_lines = "\n".join(f"{sub_id}: {descriptions.get(sub_id, '')}" for sub_id in sub_criteria)
    return (
        f"Score the following {category_name} sub-criteria based ONLY on the code above:\n"
        f"{criteria_lines}\n\n"
        "For each sub-criterion, score 0 (fails), 0.5 (partial), 1 (meets it), or null if the "
        "code snippet does not contain enough information to judge that specific sub-criterion "
        "(e.g. it asks about PR comments, commit history, or other context not present in "
        "source code -- do not guess or assume in that case, use null). "
        "Each remark must be specific to its own sub-criterion's exact wording above, not a "
        "general comment about the code as a whole or about a different sub-criterion.\n"
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )


def _code_context_message(code_snippets: str) -> str:
    return (
        "You are an expert Android code reviewer. Here is the Android project's "
        f"source code for review:\n\n{code_snippets}"
    )


def _general_remarks_prompt() -> str:
    return (
        "You are an expert Android code reviewer. Given per-criterion scores and remarks "
        "from a completed code review, write a concise 2-3 sentence overall summary of the "
        "code quality, highlighting the weakest areas. Respond with plain text only, no JSON."
    )


async def score_category(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str) -> tuple:
    if is_stub_mode():
        return _stub_score(category_name, sub_criteria, descriptions)
    return await _live_score(category_name, sub_criteria, descriptions, code_snippets)


async def generate_general_remarks(category_results: dict) -> tuple:
    if is_stub_mode():
        return _stub_general_remarks()
    return await _live_general_remarks(category_results)


def _stub_score(category_name: str, sub_criteria: list, descriptions: dict) -> tuple:
    instructions = _category_instructions(category_name, sub_criteria, descriptions)
    sub_results = {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _zero_tokens()}
    return sub_results, prompt_info


def _stub_general_remarks() -> tuple:
    text = f"{STUB_PREFIX} No Azure OpenAI key configured; general remarks not generated."
    prompt_info = {"label": "General remarks", "prompt_text": _general_remarks_prompt(), "tokens": _zero_tokens()}
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
    instructions = _category_instructions(category_name, sub_criteria, descriptions)
    payload = {
        "messages": [
            {"role": "system", "content": _code_context_message(code_snippets)},
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
        parsed = json.loads(_strip_markdown_fences(content))
        return _normalize_score_result(parsed, sub_criteria), prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return fallback, prompt_info


def _normalize_score_result(parsed: dict, sub_criteria: list) -> dict:
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


def _build_findings_summary(category_results: dict) -> str:
    lines = []
    for result in category_results.values():
        for sub_id, sub in result["sub_scores"].items():
            lines.append(f"{sub_id}: score={sub.get('score')}, remark={sub.get('remark') or ''}")
    return "\n".join(lines) if lines else "No findings were scored."


async def _live_general_remarks(category_results: dict) -> tuple:
    system_prompt = _general_remarks_prompt()
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_findings_summary(category_results)},
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


def _strip_markdown_fences(content: str) -> str:
    """Defensive fallback: response_format=json_object should prevent this, but
    strip a ```json ... ``` or ``` ... ``` wrapper if the model adds one anyway.
    """
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return match.group(1) if match else content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_openai_client.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: capture prompt text and token usage; reorder category prompts for caching"
```

---

### Task 2: Backend — wire `code_context`/`prompt_log` into the review pipeline

**Files:**
- Modify: `backend/app/api/reviews.py`
- Test: `backend/tests/test_reviews_create.py`, `backend/tests/test_reviews_progress.py`

**Interfaces:**
- Consumes: `score_category(...) -> (dict, dict)`, `generate_general_remarks(...) -> (str, dict)` (Task 1).
- Produces: `GET /api/reviews/{review_id}/progress` gains `code_context: string | null` and `prompt_log: {label, prompt_text, tokens}[]`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reviews_create.py`, update both existing `score_category` monkeypatches to return the new tuple shape. Change `test_run_review_updates_message_per_category_during_scoring`'s fake:

```python
    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        seen_messages.append(_reviews[review_id]["message"])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info
```

And `test_run_review_updates_category_scores_progressively`'s fake, the same way:

```python
    async def _recording_score_category(category_name, sub_criteria, descriptions, code_snippets):
        snapshots.append([(e["id"], e["percent_points"]) for e in _reviews[review_id]["category_scores"]])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info
```

Add a new test after `test_run_review_updates_category_scores_progressively`:

```python
async def test_run_review_builds_prompt_log_and_code_context(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "prompt-log-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()
    assert _reviews[review_id]["code_context"] is None
    assert _reviews[review_id]["prompt_log"] == []

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert "class Main {}" in state["code_context"]
    # 5 category calls + 1 general-remarks call, in that order.
    assert [entry["label"] for entry in state["prompt_log"]] == [
        "Code naming conventions / Code Structure",
        "Reliability, Security & Observability",
        "Delivery Discipline & Architecture",
        "AI Usage & Code Ownership",
        "Safe & Integrated AI Code",
        "General remarks",
    ]
    assert all(
        entry["tokens"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
        for entry in state["prompt_log"]
    )
```

In `backend/tests/test_reviews_progress.py`, extend `test_progress_reflects_stored_state`'s stored state and assertions:

```python
        "category_scores": [
            {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 90.0},
            {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
        ],
        "code_context": "class MainActivity {}",
        "prompt_log": [
            {
                "label": "Code naming conventions / Code Structure",
                "prompt_text": "Score the following...",
                "tokens": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540, "cached_tokens": None},
            },
        ],
    }
    response = client.get("/api/reviews/fixed-id/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["phase"] == "scoring"
    assert body["progress"] == 60
    assert body["download_url"] is None
    assert body["error"] is None
    assert body["warnings"] == ["Missing AndroidManifest.xml"]
    assert body["test_coverage"] == 82.5
    assert body["secrets_found"] == [{"file": "Constants.java", "line": 42, "pattern": "api_key"}]
    assert body["total_score_pct"] == 78.0
    assert body["category_scores"] == [
        {"id": "1", "name": "Code naming conventions / Code Structure", "percent_points": 90.0},
        {"id": "2", "name": "Reliability, Security & Observability", "percent_points": None},
    ]
    assert body["code_context"] == "class MainActivity {}"
    assert body["prompt_log"] == [
        {
            "label": "Code naming conventions / Code Structure",
            "prompt_text": "Score the following...",
            "tokens": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540, "cached_tokens": None},
        },
    ]
```

And extend `test_progress_defaults_detection_fields_when_absent`:

```python
    assert body["total_score_pct"] is None
    assert body["category_scores"] == []
    assert body["code_context"] is None
    assert body["prompt_log"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_reviews_create.py tests/test_reviews_progress.py -v`
Expected: `test_run_review_updates_message_per_category_during_scoring` and `test_run_review_updates_category_scores_progressively` FAIL (real `_run_review` still does `sub_results = await score_category(...)`, so a 2-tuple return from the updated fakes gets treated as a single value, not unpacked — actually at this point `_run_review` hasn't been updated yet, so it'll fail differently: unpacking mismatch once Step 3 changes `_run_review`, but right now with the OLD `_run_review` code and NEW fake returning a tuple, `scores_by_category[category_id] = aggregate_category_scores(sub_results)` would receive a tuple instead of a dict and error inside `aggregate_category_scores`). The new `test_run_review_builds_prompt_log_and_code_context` FAILS with `KeyError: 'code_context'`. The two progress tests FAIL on the new `code_context`/`prompt_log` assertions.

- [ ] **Step 3: Implement the wiring**

In `backend/app/api/reviews.py`, add the two new fields to `_new_review_state`:

```python
def _new_review_state() -> dict:
    return {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
        "warnings": [],
        "test_coverage": None,
        "secrets_found": [],
        "total_score_pct": None,
        "category_scores": [
            {"id": category_id, "name": category["name"], "percent_points": None}
            for category_id, category in CATEGORIES.items()
        ],
        "code_context": None,
        "prompt_log": [],
    }
```

Store `code_context` right after it's gathered:

```python
        code_context = gather_code_context(extract_dir)
        state["code_context"] = code_context
```

Update the scoring loop to unpack the tuple and append to `prompt_log`:

```python
        for index, (category_id, category) in enumerate(CATEGORIES.items()):
            state["message"] = f"Evaluating {category['name']}..."
            sub_results, prompt_info = await score_category(
                category["name"], category["sub_criteria"], sub_criteria_descriptions, code_context
            )
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
            state["category_scores"][index]["percent_points"] = scores_by_category[category_id]["percent_points"]
            state["prompt_log"].append(prompt_info)
            state["progress"] = 50 + int(30 * (index + 1) / category_count)
```

Update the general-remarks call:

```python
        general_remarks, remarks_prompt_info = await generate_general_remarks(scores_by_category)
        state["prompt_log"].append(remarks_prompt_info)
```

Add both fields to `get_progress`'s response:

```python
    return {
        "status": state["status"],
        "phase": state["phase"],
        "progress": state["progress"],
        "message": state["message"],
        "stats": state["stats"],
        "download_url": f"/api/reviews/{review_id}/download" if state["status"] == "completed" else None,
        "error": state["error"],
        "warnings": state.get("warnings", []),
        "test_coverage": state.get("test_coverage"),
        "secrets_found": state.get("secrets_found", []),
        "total_score_pct": state.get("total_score_pct"),
        "category_scores": state.get("category_scores", []),
        "code_context": state.get("code_context"),
        "prompt_log": state.get("prompt_log", []),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest -v`
Expected: all tests PASS (full backend suite — this also re-verifies `test_reviews_integration.py`, whose `score_category` wrapper just forwards whatever the real function returns, so it needs no changes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_progress.py
git commit -m "feat: wire code_context and prompt_log into the review pipeline and progress response"
```

---

### Task 3: Frontend — `LlmUsageStats` component

**Files:**
- Create: `frontend/src/components/LlmUsageStats.jsx`
- Test: `frontend/src/components/LlmUsageStats.test.jsx`

**Interfaces:**
- Produces: `LlmUsageStats({ promptLog })` — `promptLog: {label, prompt_text, tokens: {prompt_tokens, completion_tokens, total_tokens, cached_tokens}}[]`. Consumed by `App.jsx` (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/LlmUsageStats.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import LlmUsageStats from "./LlmUsageStats";

test("shows the call count and summed total tokens", () => {
  const promptLog = [
    {
      label: "Code naming conventions / Code Structure",
      prompt_text: "...",
      tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
    },
    {
      label: "General remarks",
      prompt_text: "...",
      tokens: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, cached_tokens: null },
    },
  ];
  render(<LlmUsageStats promptLog={promptLog} />);
  expect(screen.getByText("2 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("660 tokens used")).toBeInTheDocument();
});

test("shows a zero state for an empty prompt log", () => {
  render(<LlmUsageStats promptLog={[]} />);
  expect(screen.getByText("0 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("0 tokens used")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- LlmUsageStats --watchAll=false`
Expected: FAIL — `Cannot find module './LlmUsageStats'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/LlmUsageStats.jsx`:

```jsx
function sumTokens(promptLog) {
  return promptLog.reduce((total, entry) => total + (entry.tokens?.total_tokens ?? 0), 0);
}

export default function LlmUsageStats({ promptLog }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
      <span className="tag tag-outline">{promptLog.length} LLM calls</span>
      <span className="tag tag-outline">{sumTokens(promptLog)} tokens used</span>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- LlmUsageStats --watchAll=false`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LlmUsageStats.jsx frontend/src/components/LlmUsageStats.test.jsx
git commit -m "feat: add LlmUsageStats component"
```

---

### Task 4: Frontend — `PromptDebugLog` component

**Files:**
- Create: `frontend/src/components/PromptDebugLog.jsx`
- Test: `frontend/src/components/PromptDebugLog.test.jsx`

**Interfaces:**
- Consumes: `CornerMarks` (default export, from `./CornerMarks`).
- Produces: `PromptDebugLog({ codeContext, promptLog })` — `codeContext: string | null`, `promptLog` same shape as Task 3. Consumed by `App.jsx` (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/PromptDebugLog.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PromptDebugLog from "./PromptDebugLog";

const promptLog = [
  {
    label: "Code naming conventions / Code Structure",
    prompt_text: "Score the following...",
    tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
  },
  {
    label: "General remarks",
    prompt_text: "Given per-criterion scores...",
    tokens: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, cached_tokens: 64 },
  },
];

test("code context is collapsed by default", () => {
  render(<PromptDebugLog codeContext="class MainActivity {}" promptLog={promptLog} />);
  expect(screen.queryByText("class MainActivity {}")).not.toBeInTheDocument();
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
});

test("expands the code context on click", async () => {
  const user = userEvent.setup();
  render(<PromptDebugLog codeContext="class MainActivity {}" promptLog={promptLog} />);
  await user.click(screen.getByText(/show source code sent to the model/i));
  expect(screen.getByText("class MainActivity {}")).toBeInTheDocument();
});

test("renders every prompt log entry with its label, text, and token summary", () => {
  render(<PromptDebugLog codeContext="" promptLog={promptLog} />);
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("Score the following...")).toBeInTheDocument();
  expect(screen.getByText("500 prompt · 40 completion · 540 total")).toBeInTheDocument();
  expect(screen.getByText("General remarks")).toBeInTheDocument();
  expect(screen.getByText("100 prompt · 20 completion · 120 total · 64 cached")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- PromptDebugLog --watchAll=false`
Expected: FAIL — `Cannot find module './PromptDebugLog'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/PromptDebugLog.jsx`:

```jsx
import { useState } from "react";
import CornerMarks from "./CornerMarks";

function tokenSummary(tokens) {
  if (!tokens) return "";
  const parts = [
    `${tokens.prompt_tokens ?? 0} prompt`,
    `${tokens.completion_tokens ?? 0} completion`,
    `${tokens.total_tokens ?? 0} total`,
  ];
  if (tokens.cached_tokens) parts.push(`${tokens.cached_tokens} cached`);
  return parts.join(" · ");
}

export default function PromptDebugLog({ codeContext, promptLog }) {
  const [codeOpen, setCodeOpen] = useState(false);

  return (
    <div className="card blueprint" style={{ padding: "var(--space-4)", maxHeight: 420, overflowY: "auto" }}>
      <CornerMarks />
      <div className="card-kicker">Debug</div>
      <div className="card-title" style={{ fontSize: 20 }}>Prompts &amp; token usage</div>

      <button
        type="button"
        className="card-body"
        style={{
          textAlign: "left", background: "none", border: "none", padding: 0,
          cursor: "pointer", font: "inherit", marginTop: "var(--space-3)",
        }}
        onClick={() => setCodeOpen((open) => !open)}
      >
        {codeOpen ? "Hide" : "Show"} source code sent to the model
      </button>
      {codeOpen && (
        <pre
          style={{
            whiteSpace: "pre-wrap", fontSize: 12, maxHeight: 200, overflowY: "auto",
            background: "var(--color-surface)", padding: "var(--space-2)", marginTop: "var(--space-2)",
          }}
        >
          {codeContext}
        </pre>
      )}

      <div style={{ marginTop: "var(--space-4)", display: "grid", gap: "var(--space-3)" }}>
        {promptLog.map((entry, index) => (
          <div key={index} style={{ borderTop: "1px solid var(--color-divider)", paddingTop: "var(--space-2)" }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{entry.label}</div>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: "var(--space-1) 0" }}>{entry.prompt_text}</pre>
            <p className="text-muted" style={{ fontSize: 11, margin: 0 }}>{tokenSummary(entry.tokens)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- PromptDebugLog --watchAll=false`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/PromptDebugLog.jsx frontend/src/components/PromptDebugLog.test.jsx
git commit -m "feat: add PromptDebugLog component"
```

---

### Task 5: Frontend — simplify `StatsDisplay` (drop nested chart and findings)

**Files:**
- Modify: `frontend/src/components/StatsDisplay.jsx`
- Test: `frontend/src/components/StatsDisplay.test.jsx`

**Interfaces:**
- Produces: `StatsDisplay({ totalScorePct, warnings, secretsFound, stats, downloadUrl, onReset })` — drops `testCoverage` and `categoryScores` entirely (no longer renders `FindingsPanel` or `CategoryScoresChart` internally; both now render once, directly in `App.jsx`'s layout — Task 6). This is a breaking prop-shape change; `App.jsx` is the only caller and is updated in Task 6.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/StatsDisplay.test.jsx` entirely:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatsDisplay from "./StatsDisplay";

const baseProps = {
  totalScorePct: 78,
  warnings: [],
  secretsFound: [],
  stats: {},
  downloadUrl: "/api/reviews/abc-123/download",
  onReset: () => {},
};

test("shows timing breakdown for each provided stat, formatted as seconds", () => {
  render(
    <StatsDisplay
      {...baseProps}
      stats={{ ingest_time_ms: 800, analysis_time_ms: 2100, scoring_time_ms: 11400, generation_time_ms: 600, total_time_ms: 14900 }}
    />
  );

  expect(screen.getByText("0.8s")).toBeInTheDocument();
  expect(screen.getByText("14.9s")).toBeInTheDocument();
});

test("shows the total score tag when totalScorePct is present", () => {
  render(<StatsDisplay {...baseProps} totalScorePct={78} />);
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
});

test("omits the total score tag when totalScorePct is null", () => {
  render(<StatsDisplay {...baseProps} totalScorePct={null} />);
  expect(screen.queryByText(/^Total/)).not.toBeInTheDocument();
});

test("shows warning and secret counts as outline tags", () => {
  render(
    <StatsDisplay
      {...baseProps}
      warnings={["Missing AndroidManifest.xml"]}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText("1 warnings")).toBeInTheDocument();
  expect(screen.getByText("1 secrets")).toBeInTheDocument();
});

test("renders a download link pointing at the constructed download URL", () => {
  render(<StatsDisplay {...baseProps} />);
  const link = screen.getByRole("link", { name: /download populated workbook/i });
  expect(link).toHaveAttribute("href", "http://localhost:8000/api/reviews/abc-123/download");
  expect(link).toHaveAttribute("download");
});

test("calls onReset when Start new review is clicked", async () => {
  const user = userEvent.setup();
  const onReset = jest.fn();
  render(<StatsDisplay {...baseProps} onReset={onReset} />);
  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(onReset).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- StatsDisplay --watchAll=false`
Expected: FAIL (crash, not just an assertion mismatch) — the new `baseProps` no longer includes `categoryScores`, so the old `StatsDisplay.jsx` passes `categoryScores={undefined}` straight into its nested `<CategoryScoresChart>`, which does `categoryScores.map(...)` and throws `TypeError: Cannot read properties of undefined (reading 'map')`. Every test in the file fails with this error until Step 3 removes the nested chart.

- [ ] **Step 3: Implement the simplified component**

Replace `frontend/src/components/StatsDisplay.jsx` entirely:

```jsx
import CornerMarks from "./CornerMarks";
import { DownloadIcon } from "../icons";
import { getDownloadUrl } from "../services/api";

function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

const TIMING_ROWS = [
  { key: "ingest_time_ms", label: "Ingest (unzip + validate)" },
  { key: "analysis_time_ms", label: "Analysis (parsing + secrets + versions)" },
  { key: "scoring_time_ms", label: "Scoring (Azure OpenAI)" },
  { key: "generation_time_ms", label: "Generation (Excel write)" },
  { key: "total_time_ms", label: "Total" },
];

export default function StatsDisplay({ totalScorePct, warnings, secretsFound, stats, downloadUrl, onReset }) {
  const rows = TIMING_ROWS.filter((row) => stats[row.key] !== undefined);

  return (
    <div>
      <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
        <CornerMarks />
        <div className="card-kicker">Complete</div>
        <div className="card-title" style={{ fontSize: 20 }}>Review ready</div>
        <p className="card-body">Scores were written into your template with the original formatting preserved.</p>
        <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
          {totalScorePct !== null && totalScorePct !== undefined && (
            <span className="tag tag-accent">Total {totalScorePct}%</span>
          )}
          <span className="tag tag-outline">{warnings.length} warnings</span>
          <span className="tag tag-outline">{secretsFound.length} secrets</span>
        </div>
        <a
          href={getDownloadUrl(downloadUrl)}
          download
          className="btn btn-primary btn-block blueprint"
          style={{ marginTop: "var(--space-5)" }}
        >
          <CornerMarks />
          Download populated workbook
          <DownloadIcon />
        </a>
      </div>

      <div className="card blueprint" style={{ padding: "var(--space-6)", marginTop: "var(--space-5)" }}>
        <CornerMarks />
        <div className="card-kicker">Timing</div>
        <div className="card-title" style={{ fontSize: 20 }}>Performance breakdown</div>
        <table className="table" style={{ marginTop: "var(--space-4)" }}>
          <thead><tr><th>Phase</th><th>Duration</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>{row.label}</td>
                <td className="text-muted">{formatSeconds(stats[row.key])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button type="button" className="btn btn-ghost" style={{ marginTop: "var(--space-5)" }} onClick={onReset}>
        Start new review
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- StatsDisplay --watchAll=false`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatsDisplay.jsx frontend/src/components/StatsDisplay.test.jsx
git commit -m "refactor: simplify StatsDisplay, drop nested chart/findings now rendered once in App layout"
```

---

### Task 6: Frontend — 2-band layout in `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: `CategoryScoresChart` (existing), `LlmUsageStats`/`PromptDebugLog` (Tasks 3-4), simplified `StatsDisplay` (Task 5).
- Produces: the complete running/completed page layout — no new external interface; this is the app's root component.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/App.test.jsx` entirely:

```jsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { createReview, getProgress } from "./services/api";

jest.mock("./services/api", () => ({
  ...jest.requireActual("./services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

async function uploadValidFiles(user) {
  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));
}

test("full happy path: upload, poll, complete, download link, LLM stats, reset", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
    category_scores: [
      { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
    ],
    code_context: "class MainActivity {}",
    prompt_log: [
      {
        label: "Code naming conventions / Code Structure",
        prompt_text: "Score the following...",
        tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
      },
    ],
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/review ready/i)).toBeInTheDocument();
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("1 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("540 tokens used")).toBeInTheDocument();
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /download populated workbook/i })).toHaveAttribute(
    "href",
    "http://localhost:8000/api/reviews/abc-123/download"
  );

  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("shows an error message when review creation fails", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockRejectedValue(new Error("network error"));

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/failed to start review/i)).toBeInTheDocument();
});

test("shows an error message when the review itself fails during processing, and Try again resets to idle", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "error", phase: "error", progress: 0, message: "Queued",
    stats: {}, download_url: null, error: "No source files found (.java/.kt)",
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    category_scores: [], code_context: null, prompt_log: [],
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText("No source files found (.java/.kt)")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /try again/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && CI=true npm test -- App.test --watchAll=false`
Expected: FAIL — the current `App.jsx` still calls `StatsDisplay` with the old prop shape (`testCoverage`/`categoryScores`) removed in Task 5, and doesn't render `LlmUsageStats`/`PromptDebugLog` at all, so those assertions won't find matching text.

- [ ] **Step 3: Implement the 2-band layout**

Replace `frontend/src/App.jsx` entirely:

```jsx
import { useCallback, useState } from "react";
import UploadForm from "./components/UploadForm";
import ProgressTracker from "./components/ProgressTracker";
import FindingsPanel from "./components/FindingsPanel";
import CategoryScoresChart from "./components/CategoryScoresChart";
import LlmUsageStats from "./components/LlmUsageStats";
import PromptDebugLog from "./components/PromptDebugLog";
import StatsDisplay from "./components/StatsDisplay";
import CornerMarks from "./components/CornerMarks";
import { createReview } from "./services/api";

const SCORING_PHASES = ["scoring", "generating", "completed"];

export default function App() {
  const [state, setState] = useState("idle"); // idle | uploading | polling | completed | error
  const [reviewId, setReviewId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  const handleUpload = useCallback(async (androidZip, excelTemplate) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const result = await createReview(androidZip, excelTemplate);
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

  const handleProgressUpdate = useCallback((data) => {
    setProgressData(data);
    if (data.status === "completed") {
      setState("completed");
    } else if (data.status === "error") {
      setErrorMessage(data.error || "Review failed");
      setState("error");
    }
  }, []);

  function handleReset() {
    setState("idle");
    setReviewId(null);
    setProgressData(null);
    setErrorMessage("");
  }

  const isRunningOrDone = state === "polling" || state === "completed";
  const showLlmDetails = !!progressData && SCORING_PHASES.includes(progressData.phase);

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav"><span className="nav-brand">Code Review Automation</span></nav>

      <main style={{ maxWidth: isRunningOrDone ? 1440 : 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            Android Code Review Automation
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Upload an Android project and a scoring template. The reviewer analyzes structure, security, tests and
            dependency versions, scores each category with AI, and hands back a populated workbook.
          </p>
        </header>

        {(state === "idle" || state === "uploading") && (
          <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} />
        )}

        {isRunningOrDone && reviewId && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
              <div>
                {state === "polling" && (
                  <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
                )}
                {progressData && (
                  <div style={{ marginTop: state === "polling" ? "var(--space-5)" : 0 }}>
                    <FindingsPanel
                      warnings={progressData.warnings}
                      testCoverage={progressData.test_coverage}
                      secretsFound={progressData.secrets_found}
                    />
                  </div>
                )}
                {state === "completed" && progressData && (
                  <div style={{ marginTop: "var(--space-5)" }}>
                    <StatsDisplay
                      totalScorePct={progressData.total_score_pct}
                      warnings={progressData.warnings}
                      secretsFound={progressData.secrets_found}
                      stats={progressData.stats}
                      downloadUrl={progressData.download_url}
                      onReset={handleReset}
                    />
                  </div>
                )}
              </div>

              <div>
                {showLlmDetails && (
                  <>
                    <CategoryScoresChart categoryScores={progressData.category_scores} />
                    <div style={{ marginTop: "var(--space-4)" }}>
                      <LlmUsageStats promptLog={progressData.prompt_log} />
                    </div>
                  </>
                )}
              </div>
            </div>

            {showLlmDetails && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <PromptDebugLog codeContext={progressData.code_context} promptLog={progressData.prompt_log} />
              </div>
            )}
          </>
        )}

        {state === "error" && (
          <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
            <CornerMarks />
            <div className="card-kicker">Error</div>
            <div className="card-title" style={{ fontSize: 20 }}>Review failed</div>
            <p className="card-body">{errorMessage}</p>
            <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
              <button type="button" className="btn btn-primary blueprint" onClick={handleReset}>
                <CornerMarks />
                Try again
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npm test -- --watchAll=false`
Expected: the ENTIRE frontend suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat: rework App into a 2-band layout with LLM usage stats and prompt debug log"
```

---

## Final Verification

```bash
cd backend && source venv/bin/activate && pytest -v
cd frontend && CI=true npm test -- --watchAll=false
```

Both must PASS with zero failures before considering this plan complete.

## Manual Check

Because this plan changes prompt structure sent to a real Azure OpenAI deployment, after implementation run one real (non-stub) review against a live `AZURE_OPENAI_KEY` if available, and confirm in the debug log that: category rubric text looks correct, token counts are non-zero and sane, and (if the deployment supports it) `cached_tokens` becomes non-zero on categories 2-5 (category 1's call has nothing to cache yet, since it's the first request with that code prefix).

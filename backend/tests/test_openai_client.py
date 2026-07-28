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

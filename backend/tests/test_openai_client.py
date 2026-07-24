import httpx
import pytest

from app.analyzer import openai_client


@pytest.mark.asyncio
async def test_stub_mode_returns_placeholder_scores(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    result = await openai_client.score_category("Code Structure", ["1.1", "1.2"], "code here")
    assert set(result.keys()) == {"1.1", "1.2"}
    for sub in result.values():
        assert sub["score"] == 1
        assert sub["remark"].startswith("[STUB]")


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
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await openai_client.score_category("Code Structure", ["1.1"], "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}
    assert captured["headers"]["api-key"] == "test-key"
    assert "gpt-4o-mini" in captured["url"]
    assert captured["json"]["temperature"] == 0.3
    assert captured["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_live_mode_strips_markdown_fences_if_model_adds_them_anyway(monkeypatch):
    # Verified against the real Azure deployment: with 6 sub-criteria the model
    # sometimes wraps its JSON in ```json ... ``` even with response_format set.
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        content = '```json\n{"1.1": {"score": 1, "remark": "Well named"}}\n```'
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await openai_client.score_category("Code Structure", ["1.1"], "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}


@pytest.mark.asyncio
async def test_live_mode_falls_back_on_malformed_response_envelope(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.cognitive.microsoft.com/")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")

    async def fake_post(self, url, headers=None, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={"unexpected": "shape"},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await openai_client.score_category("Code Structure", ["1.1", "1.2"], "code here")

    assert result == {
        "1.1": {"score": None, "remark": ""},
        "1.2": {"score": None, "remark": ""},
    }


@pytest.mark.asyncio
async def test_generate_general_remarks_stub_mode(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    result = await openai_client.generate_general_remarks({})
    assert result.startswith("[STUB]")


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
        return httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    category_results = {
        "1": {"sub_scores": {"1.1": {"score": 1, "remark": "Good naming"}}},
        "2": {"sub_scores": {"2.1": {"score": 0, "remark": "No exception handling"}}},
    }
    result = await openai_client.generate_general_remarks(category_results)

    assert result == "Overall code quality is solid, with weak exception handling."
    assert "1.1: score=1, remark=Good naming" in captured["json"]["messages"][1]["content"]
    assert "response_format" not in captured["json"]


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

    result = await openai_client.generate_general_remarks({})
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

    result = await openai_client.score_category("Code Structure", ["1.1"], "code here")

    assert result == {"1.1": {"score": None, "remark": ""}}
    assert call_count["n"] == 3

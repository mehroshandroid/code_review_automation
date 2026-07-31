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


@pytest.mark.asyncio
async def test_score_category_falls_back_on_connection_error(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    call_count = {"n": 0}

    async def fake_post(self, url, json=None):
        call_count["n"] += 1
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
    # Falls back only after a retry -- not on the very first failure.
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_score_category_retries_once_after_a_transient_timeout_before_falling_back(monkeypatch):
    # A local LLM occasionally taking longer than TIMEOUT_SECONDS for one
    # category (slower hardware, a bigger prompt, model cold-start) used to
    # silently score that category None forever -- indistinguishable from
    # "not scored yet" in the UI. A single retry recovers from exactly this
    # kind of transient, one-off timeout instead of giving up immediately.
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://fake-ollama:11434")
    call_count = {"n": 0}

    async def fake_post(self, url, json=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.ConnectTimeout("timed out", request=httpx.Request("POST", url))
        content = '{"1.1": {"score": 1, "remark": "Recovered after retry"}}'
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": content}}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, _ = await ollama_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": 1, "remark": "Recovered after retry"}}
    assert call_count["n"] == 2


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

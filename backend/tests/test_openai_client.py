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

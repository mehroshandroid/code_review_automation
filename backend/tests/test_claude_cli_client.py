import httpx
import pytest

from app.analyzer import claude_cli_client


@pytest.mark.asyncio
async def test_score_category_calls_the_agent_and_parses_response(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_AGENT_URL", "http://fake-agent:8200")
    captured = {}

    async def fake_post(self, url, json=None):
        captured["url"] = url
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={"status": "ok", "result": '{"1.1": {"score": 1, "remark": "Well named"}}'},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await claude_cli_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": 1, "remark": "Well named"}}
    assert captured["url"] == "http://fake-agent:8200/ask"
    assert "code here" in captured["json"]["prompt"]
    assert prompt_info["label"] == "Code Structure"


async def test_score_category_falls_back_to_a_placeholder_score_when_the_agent_is_unreachable(monkeypatch):
    async def fake_post(self, url, json=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await claude_cli_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result["1.1"]["score"] == 1
    assert "[STUB]" in result["1.1"]["remark"]


async def test_score_category_falls_back_to_a_placeholder_score_when_the_agent_reports_an_error(monkeypatch):
    async def fake_post(self, url, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"status": "error", "message": "claude CLI timed out."}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await claude_cli_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result["1.1"]["score"] == 1
    assert "claude CLI timed out." in result["1.1"]["remark"]


async def test_score_category_returns_null_scores_when_the_result_is_not_valid_json(monkeypatch):
    async def fake_post(self, url, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"status": "ok", "result": "not json"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result, prompt_info = await claude_cli_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert result == {"1.1": {"score": None, "remark": ""}}


async def test_generate_general_remarks_calls_the_agent_and_returns_the_text(monkeypatch):
    captured = {}

    async def fake_post(self, url, json=None):
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(status_code=200, json={"status": "ok", "result": "  Great structure overall.  "}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    text, prompt_info = await claude_cli_client.generate_general_remarks({})

    assert text == "Great structure overall."
    assert prompt_info["label"] == "General remarks"


async def test_generate_general_remarks_falls_back_to_a_placeholder_when_the_agent_is_unreachable(monkeypatch):
    async def fake_post(self, url, json=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    text, prompt_info = await claude_cli_client.generate_general_remarks({})

    assert "[STUB]" in text

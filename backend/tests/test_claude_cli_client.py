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


def test_extract_usage_sums_all_three_input_token_counts_as_prompt_tokens():
    response = {
        "status": "ok",
        "usage": {
            "input_tokens": 2, "cache_creation_input_tokens": 25213, "cache_read_input_tokens": 100, "output_tokens": 12,
        },
    }

    assert claude_cli_client._extract_usage(response) == {
        "prompt_tokens": 25315, "completion_tokens": 12, "total_tokens": 25327, "cached_tokens": 100,
    }


def test_extract_usage_returns_empty_tokens_when_usage_is_missing():
    assert claude_cli_client._extract_usage({"status": "ok", "result": "x"}) == {
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None,
    }


async def test_score_category_reports_real_token_usage_on_success(monkeypatch):
    async def fake_post(self, url, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={
                "status": "ok", "result": '{"1.1": {"score": 1, "remark": "Well named"}}',
                "usage": {"input_tokens": 2, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 0, "output_tokens": 12},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _, prompt_info = await claude_cli_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert prompt_info["tokens"] == {
        "prompt_tokens": 102, "completion_tokens": 12, "total_tokens": 114, "cached_tokens": 0,
    }


async def test_score_category_reports_empty_tokens_when_the_agent_is_unreachable(monkeypatch):
    async def fake_post(self, url, json=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _, prompt_info = await claude_cli_client.score_category("Code Structure", ["1.1"], {}, "code here")

    assert prompt_info["tokens"] == {
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None,
    }


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


async def test_generate_general_remarks_reports_real_token_usage_on_success(monkeypatch):
    async def fake_post(self, url, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=200,
            json={
                "status": "ok", "result": "Great structure overall.",
                "usage": {"input_tokens": 1, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 10, "output_tokens": 8},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _, prompt_info = await claude_cli_client.generate_general_remarks({})

    assert prompt_info["tokens"] == {
        "prompt_tokens": 61, "completion_tokens": 8, "total_tokens": 69, "cached_tokens": 10,
    }


async def test_generate_general_remarks_falls_back_to_a_placeholder_when_the_agent_is_unreachable(monkeypatch):
    async def fake_post(self, url, json=None):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    text, prompt_info = await claude_cli_client.generate_general_remarks({})

    assert "[STUB]" in text

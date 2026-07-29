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

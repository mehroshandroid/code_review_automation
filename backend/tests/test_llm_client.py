import pytest

from app.analyzer import llm_client


@pytest.mark.asyncio
async def test_score_category_routes_to_ollama_when_provider_is_ollama(monkeypatch):
    captured = {}

    async def fake_ollama_score_category(category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured["args"] = (category_name, sub_criteria, descriptions, code_snippets, model)
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "score_category", fake_ollama_score_category)

    result, _ = await llm_client.score_category("ollama", "Code Structure", ["1.1"], {}, "code", model="mistral:latest")

    assert result == {"1.1": {"score": 1, "remark": "ok"}}
    assert captured["args"] == ("Code Structure", ["1.1"], {}, "code", "mistral:latest")


@pytest.mark.asyncio
async def test_score_category_routes_to_openai_for_any_non_ollama_provider(monkeypatch):
    calls = []

    async def fake_openai_score_category(category_name, sub_criteria, descriptions, code_snippets, platform="Android", checklists=None):
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

    async def fake_ollama_general_remarks(category_results, model=None, platform="Android"):
        captured["args"] = (category_results, model)
        return "ollama summary", {"label": "General remarks", "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "generate_general_remarks", fake_ollama_general_remarks)

    result, _ = await llm_client.generate_general_remarks("ollama", {"1": {}}, model="mistral:latest")

    assert result == "ollama summary"
    assert captured["args"] == ({"1": {}}, "mistral:latest")


@pytest.mark.asyncio
async def test_generate_general_remarks_routes_to_openai_by_default(monkeypatch):
    async def fake_openai_general_remarks(category_results, platform="Android"):
        return "azure summary", {"label": "General remarks", "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.openai_client, "generate_general_remarks", fake_openai_general_remarks)

    result, _ = await llm_client.generate_general_remarks("azure", {"1": {}})

    assert result == "azure summary"


@pytest.mark.asyncio
async def test_score_category_forwards_platform_to_whichever_provider_is_routed_to(monkeypatch):
    captured_ollama = {}
    captured_openai = {}

    async def fake_ollama_score_category(category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_ollama["platform"] = platform
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    async def fake_openai_score_category(category_name, sub_criteria, descriptions, code_snippets, platform="Android", checklists=None):
        captured_openai["platform"] = platform
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "score_category", fake_ollama_score_category)
    monkeypatch.setattr(llm_client.openai_client, "score_category", fake_openai_score_category)

    await llm_client.score_category("ollama", "Code Structure", ["1.1"], {}, "code", platform="iOS")
    await llm_client.score_category("azure", "Code Structure", ["1.1"], {}, "code", platform="iOS")

    assert captured_ollama["platform"] == "iOS"
    assert captured_openai["platform"] == "iOS"


@pytest.mark.asyncio
async def test_score_category_forwards_checklists_to_whichever_provider_is_routed_to(monkeypatch):
    captured_ollama = {}
    captured_openai = {}
    checklists = {(".NET", "2.4"): "check JWT config"}

    async def fake_ollama_score_category(category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_ollama["checklists"] = checklists
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    async def fake_openai_score_category(category_name, sub_criteria, descriptions, code_snippets, platform="Android", checklists=None):
        captured_openai["checklists"] = checklists
        return {"1.1": {"score": 1, "remark": "ok"}}, {"label": category_name, "prompt_text": "x", "tokens": {}}

    monkeypatch.setattr(llm_client.ollama_client, "score_category", fake_ollama_score_category)
    monkeypatch.setattr(llm_client.openai_client, "score_category", fake_openai_score_category)

    await llm_client.score_category("ollama", "Code Structure", ["1.1"], {}, "code", checklists=checklists)
    await llm_client.score_category("azure", "Code Structure", ["1.1"], {}, "code", checklists=checklists)

    assert captured_ollama["checklists"] == checklists
    assert captured_openai["checklists"] == checklists


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

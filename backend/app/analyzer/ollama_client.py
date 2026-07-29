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

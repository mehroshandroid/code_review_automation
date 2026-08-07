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
# Ollama defaults every model to num_ctx=2048 tokens (~8,000 characters) as
# an intentional hardware-safety default, not a model capability limit --
# nothing about the model itself caps it there. 16384 (8x the default)
# comfortably covers a category's code context + instructions without going
# all the way to the model's theoretical 32K ceiling, since num_ctx memory
# cost scales with context size and local hardware is already the
# bottleneck (see TIMEOUT_SECONDS below).
DEFAULT_OLLAMA_NUM_CTX = 16384
# Local hardware varies a lot more than a hosted API -- a 7B model on a
# laptop CPU/GPU can genuinely take several minutes for a category with a
# large code-context prompt, especially on a cold start.
TIMEOUT_SECONDS = 300.0
MAX_ATTEMPTS = 2


def _base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def _model(model: str | None) -> str:
    return model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


def _num_ctx() -> int:
    return int(os.environ.get("OLLAMA_NUM_CTX", DEFAULT_OLLAMA_NUM_CTX))


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
    # A single retry on a transient connection error or timeout -- a local
    # model occasionally running slow for one request shouldn't permanently
    # zero out that category's score (see MAX_ATTEMPTS usage below).
    url = f"{_base_url()}/v1/chat/completions"
    # num_ctx is a top-level field on this OpenAI-compatible endpoint, not
    # nested under "options" (that nesting only applies to Ollama's native
    # /api/generate and /api/chat endpoints, which this client doesn't use).
    payload = {**payload, "num_ctx": _num_ctx()}
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response
        except (httpx.HTTPError, OSError):
            if attempt == MAX_ATTEMPTS - 1:
                return None


async def score_category(
    category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    model: str | None = None, platform: str = "Android",
) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform)
    payload = {
        "model": _model(model),
        "messages": [
            {"role": "system", "content": code_context_message(code_snippets, platform)},
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


async def generate_general_remarks(category_results: dict, model: str | None = None, platform: str = "Android") -> tuple:
    system_prompt = general_remarks_prompt(platform)
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

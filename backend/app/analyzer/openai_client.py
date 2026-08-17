import asyncio
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

STUB_PREFIX = "[STUB]"


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")


def _zero_tokens() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0}


def _empty_tokens() -> dict:
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None}


def _extract_usage(response) -> dict:
    if response is None:
        return _empty_tokens()
    usage = response.json().get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": details.get("cached_tokens"),
    }


async def score_category(
    category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    platform: str = "Android", checklists: dict | None = None,
) -> tuple:
    if is_stub_mode():
        return _stub_score(category_name, sub_criteria, descriptions, platform, checklists)
    return await _live_score(category_name, sub_criteria, descriptions, code_snippets, platform, checklists)


async def generate_general_remarks(category_results: dict, platform: str = "Android") -> tuple:
    if is_stub_mode():
        return _stub_general_remarks(platform)
    return await _live_general_remarks(category_results, platform)


def _stub_score(category_name: str, sub_criteria: list, descriptions: dict, platform: str = "Android", checklists: dict | None = None) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform, checklists=checklists)
    sub_results = {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _zero_tokens()}
    return sub_results, prompt_info


def _stub_general_remarks(platform: str = "Android") -> tuple:
    text = f"{STUB_PREFIX} No Azure OpenAI key configured; general remarks not generated."
    prompt_info = {"label": "General remarks", "prompt_text": general_remarks_prompt(platform), "tokens": _zero_tokens()}
    return text, prompt_info


async def _post_with_retry(payload: dict):
    api_base = os.environ["OPENAI_API_BASE"].rstrip("/")
    deployment = os.environ["OPENAI_DEPLOYMENT_NAME"]
    api_version = os.environ["OPENAI_API_VERSION"]
    url = f"{api_base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    headers = {"api-key": os.environ["AZURE_OPENAI_KEY"], "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = None
        for attempt in range(3):
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            break
        if response is None or response.status_code == 429:
            return None
        response.raise_for_status()
        return response


async def _live_score(
    category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    platform: str = "Android", checklists: dict | None = None,
) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform, checklists=checklists)
    payload = {
        "messages": [
            {"role": "system", "content": code_context_message(code_snippets, platform)},
            {"role": "user", "content": instructions},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}

    response = await _post_with_retry(payload)
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _extract_usage(response)}
    if response is None:
        return fallback, prompt_info

    try:
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(strip_markdown_fences(content))
        return normalize_score_result(parsed, sub_criteria), prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return fallback, prompt_info


async def _live_general_remarks(category_results: dict, platform: str = "Android") -> tuple:
    system_prompt = general_remarks_prompt(platform)
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_findings_summary(category_results)},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }

    response = await _post_with_retry(payload)
    prompt_info = {"label": "General remarks", "prompt_text": system_prompt, "tokens": _extract_usage(response)}
    if response is None:
        return "", prompt_info

    try:
        text = response.json()["choices"][0]["message"]["content"].strip()
        return text, prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return "", prompt_info

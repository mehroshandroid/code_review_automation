import asyncio
import json
import os
import re

import httpx

STUB_PREFIX = "[STUB]"


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")


async def score_category(category_name: str, sub_criteria: list, code_snippets: str) -> dict:
    if is_stub_mode():
        return _stub_score(sub_criteria)
    return await _live_score(category_name, sub_criteria, code_snippets)


async def generate_general_remarks(category_results: dict) -> str:
    if is_stub_mode():
        return f"{STUB_PREFIX} No Azure OpenAI key configured; general remarks not generated."
    return await _live_general_remarks(category_results)


def _stub_score(sub_criteria: list) -> dict:
    return {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }


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


async def _live_score(category_name: str, sub_criteria: list, code_snippets: str) -> dict:
    system_prompt = (
        f"You are an expert Android code reviewer. Score {category_name} sub-criteria "
        f"{', '.join(sub_criteria)} on a scale of 0, 0.5, 1, or null if you cannot evaluate. "
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": code_snippets},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}

    response = await _post_with_retry(payload)
    if response is None:
        return fallback

    try:
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_markdown_fences(content))
    except (ValueError, KeyError, IndexError, TypeError):
        return fallback


def _build_findings_summary(category_results: dict) -> str:
    lines = []
    for result in category_results.values():
        for sub_id, sub in result["sub_scores"].items():
            lines.append(f"{sub_id}: score={sub.get('score')}, remark={sub.get('remark') or ''}")
    return "\n".join(lines) if lines else "No findings were scored."


async def _live_general_remarks(category_results: dict) -> str:
    system_prompt = (
        "You are an expert Android code reviewer. Given per-criterion scores and remarks "
        "from a completed code review, write a concise 2-3 sentence overall summary of the "
        "code quality, highlighting the weakest areas. Respond with plain text only, no JSON."
    )
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_findings_summary(category_results)},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }

    response = await _post_with_retry(payload)
    if response is None:
        return ""

    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError):
        return ""


def _strip_markdown_fences(content: str) -> str:
    """Defensive fallback: response_format=json_object should prevent this, but
    strip a ```json ... ``` or ``` ... ``` wrapper if the model adds one anyway.
    """
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return match.group(1) if match else content

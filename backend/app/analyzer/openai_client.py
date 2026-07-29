import asyncio
import json
import os
import re

import httpx

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


def _category_instructions(category_name: str, sub_criteria: list, descriptions: dict) -> str:
    criteria_lines = "\n".join(f"{sub_id}: {descriptions.get(sub_id, '')}" for sub_id in sub_criteria)
    return (
        f"Score the following {category_name} sub-criteria based ONLY on the code above:\n"
        f"{criteria_lines}\n\n"
        "For each sub-criterion, score 0 (fails), 1 (meets it), or null if the "
        "code snippet does not contain enough information to judge that specific sub-criterion "
        "(e.g. it asks about PR comments, commit history, or other context not present in "
        "source code -- do not guess or assume in that case, use null). "
        "Each remark must be specific to its own sub-criterion's exact wording above, not a "
        "general comment about the code as a whole or about a different sub-criterion.\n"
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )


def _code_context_message(code_snippets: str) -> str:
    return (
        "You are an expert Android code reviewer. Here is the Android project's "
        f"source code for review:\n\n{code_snippets}"
    )


def _general_remarks_prompt() -> str:
    return (
        "You are an expert Android code reviewer. Given per-criterion scores and remarks "
        "from a completed code review, write a concise 2-3 sentence overall summary of the "
        "code quality, highlighting the weakest areas. Respond with plain text only, no JSON."
    )


async def score_category(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str) -> tuple:
    if is_stub_mode():
        return _stub_score(category_name, sub_criteria, descriptions)
    return await _live_score(category_name, sub_criteria, descriptions, code_snippets)


async def generate_general_remarks(category_results: dict) -> tuple:
    if is_stub_mode():
        return _stub_general_remarks()
    return await _live_general_remarks(category_results)


def _stub_score(category_name: str, sub_criteria: list, descriptions: dict) -> tuple:
    instructions = _category_instructions(category_name, sub_criteria, descriptions)
    sub_results = {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _zero_tokens()}
    return sub_results, prompt_info


def _stub_general_remarks() -> tuple:
    text = f"{STUB_PREFIX} No Azure OpenAI key configured; general remarks not generated."
    prompt_info = {"label": "General remarks", "prompt_text": _general_remarks_prompt(), "tokens": _zero_tokens()}
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


async def _live_score(category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str) -> tuple:
    instructions = _category_instructions(category_name, sub_criteria, descriptions)
    payload = {
        "messages": [
            {"role": "system", "content": _code_context_message(code_snippets)},
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
        parsed = json.loads(_strip_markdown_fences(content))
        return _normalize_score_result(parsed, sub_criteria), prompt_info
    except (ValueError, KeyError, IndexError, TypeError):
        return fallback, prompt_info


def _normalize_score_result(parsed: dict, sub_criteria: list) -> dict:
    """Guarantees the returned dict has exactly sub_criteria's keys, in that
    exact order -- regardless of what order (or completeness) the model's
    JSON used. Callers rely on this order to align each sub-criterion's
    score/remark to the correct row when writing the Excel output
    positionally; a model that reorders, skips, or hallucinates an extra key
    would otherwise silently misalign every row after the discrepancy.
    """
    result = {}
    for sub_id in sub_criteria:
        entry = parsed.get(sub_id) if isinstance(parsed, dict) else None
        if isinstance(entry, dict):
            result[sub_id] = {"score": entry.get("score"), "remark": entry.get("remark", "")}
        else:
            result[sub_id] = {"score": None, "remark": ""}
    return result


def _build_findings_summary(category_results: dict) -> str:
    lines = []
    for result in category_results.values():
        for sub_id, sub in result["sub_scores"].items():
            lines.append(f"{sub_id}: score={sub.get('score')}, remark={sub.get('remark') or ''}")
    return "\n".join(lines) if lines else "No findings were scored."


async def _live_general_remarks(category_results: dict) -> tuple:
    system_prompt = _general_remarks_prompt()
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_findings_summary(category_results)},
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


def _strip_markdown_fences(content: str) -> str:
    """Defensive fallback: response_format=json_object should prevent this, but
    strip a ```json ... ``` or ``` ... ``` wrapper if the model adds one anyway.
    """
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return match.group(1) if match else content

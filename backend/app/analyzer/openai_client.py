import asyncio
import json
import os

import httpx

STUB_PREFIX = "[STUB]"


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")


async def score_category(category_name: str, sub_criteria: list, code_snippets: str) -> dict:
    if is_stub_mode():
        return _stub_score(sub_criteria)
    return await _live_score(category_name, sub_criteria, code_snippets)


def _stub_score(sub_criteria: list) -> dict:
    return {
        sub_id: {"score": 1, "remark": f"{STUB_PREFIX} No Azure OpenAI key configured; placeholder score."}
        for sub_id in sub_criteria
    }


async def _live_score(category_name: str, sub_criteria: list, code_snippets: str) -> dict:
    api_base = os.environ["OPENAI_API_BASE"].rstrip("/")
    deployment = os.environ["OPENAI_DEPLOYMENT_NAME"]
    api_version = os.environ["OPENAI_API_VERSION"]
    url = f"{api_base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    headers = {"api-key": os.environ["AZURE_OPENAI_KEY"], "Content-Type": "application/json"}
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
    }

    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = None
        for attempt in range(3):
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            break
        if response is None or response.status_code == 429:
            return fallback
        response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except ValueError:
        return fallback

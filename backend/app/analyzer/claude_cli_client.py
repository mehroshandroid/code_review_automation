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
from app.utils.logger import get_logger

DEFAULT_CLAUDE_CLI_AGENT_URL = "http://host.docker.internal:8200"
TIMEOUT_SECONDS = 300.0
STUB_PREFIX = "[STUB]"
logger = get_logger(__name__)


def _base_url() -> str:
    return os.environ.get("CLAUDE_CLI_AGENT_URL", DEFAULT_CLAUDE_CLI_AGENT_URL).rstrip("/")


def _empty_tokens() -> dict:
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cached_tokens": None}


async def _ask(prompt: str) -> dict:
    url = f"{_base_url()}/ask"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json={"prompt": prompt})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("claude_cli_client: claude_cli_agent unreachable at %s: %s", url, exc)
        return {"status": "error", "message": "claude_cli_agent is not reachable -- is it running?"}


async def score_category(
    category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str,
    platform: str = "Android", checklists: dict | None = None,
) -> tuple:
    instructions = category_instructions(category_name, sub_criteria, descriptions, platform, checklists=checklists)
    prompt = f"{code_context_message(code_snippets, platform)}\n\n{instructions}"
    prompt_info = {"label": category_name, "prompt_text": instructions, "tokens": _empty_tokens()}

    response = await _ask(prompt)
    if response.get("status") != "ok":
        message = response.get("message", "claude_cli_agent error")
        logger.warning("claude_cli_client: score_category(%s) got a non-ok response: %s", category_name, message)
        sub_results = {sub_id: {"score": 1, "remark": f"{STUB_PREFIX} {message}"} for sub_id in sub_criteria}
        return sub_results, prompt_info

    fallback = {sub_id: {"score": None, "remark": ""} for sub_id in sub_criteria}
    try:
        parsed = json.loads(strip_markdown_fences(response["result"]))
        return normalize_score_result(parsed, sub_criteria), prompt_info
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "claude_cli_client: score_category(%s) could not parse claude's result as JSON (%s). Raw result: %r",
            category_name, exc, response.get("result", "")[:2000],
        )
        return fallback, prompt_info


async def generate_general_remarks(category_results: dict, platform: str = "Android") -> tuple:
    system_prompt = general_remarks_prompt(platform)
    prompt = f"{system_prompt}\n\n{build_findings_summary(category_results)}"
    prompt_info = {"label": "General remarks", "prompt_text": system_prompt, "tokens": _empty_tokens()}

    response = await _ask(prompt)
    if response.get("status") != "ok":
        message = response.get("message", "claude_cli_agent error")
        logger.warning("claude_cli_client: generate_general_remarks got a non-ok response: %s", message)
        return f"{STUB_PREFIX} {message}", prompt_info

    return response.get("result", "").strip(), prompt_info

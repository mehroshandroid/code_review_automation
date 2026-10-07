import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 300
# Claude's own internal response construction can genuinely need several
# turns to finalize an answer to a single, non-agentic question -- a real
# scoring prompt was reproduced needing 5 turns before finishing (not a
# tool-use loop; --restricted blocks all tool use regardless of turn
# count). A low, guessed turn limit just truncates a response mid-way
# (confirmed: max_turns=1 and max_turns=3 both failed with
# "error_max_turns" and an empty result on prompts this app actually
# sends). Bounding cost via --max-budget-usd instead of a turn count is
# the real safety backstop here; MAX_TURNS stays generous so normal
# completion is never cut short.
MAX_TURNS = 10
MAX_BUDGET_USD = 1.00
logger = logging.getLogger("uvicorn.error")


async def _run_subprocess(command: list, cwd: Path, timeout_seconds: float) -> dict:
    try:
        process = await asyncio.create_subprocess_exec(
            *command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": f"Failed to start process: {exc}"}

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {"returncode": None, "stdout": "", "stderr": "claude CLI process timed out."}

    return {
        "returncode": process.returncode,
        "stdout": stdout.decode(errors="replace"),
        "stderr": stderr.decode(errors="replace"),
    }


def _parse_claude_output(run_result: dict) -> dict:
    if run_result["returncode"] != 0:
        message = run_result["stderr"].strip() or "claude CLI exited with a non-zero status."
        logger.warning("claude_runner: claude CLI exited %s: %s", run_result["returncode"], message)
        return {"status": "error", "message": message}

    try:
        parsed = json.loads(run_result["stdout"])
    except ValueError:
        logger.warning("claude_runner: claude CLI stdout wasn't valid JSON: %r", run_result["stdout"][:2000])
        return {"status": "error", "message": "claude CLI returned output that wasn't valid JSON."}

    if parsed.get("is_error"):
        message = parsed.get("result") or "claude CLI reported an error."
        logger.warning("claude_runner: claude CLI reported is_error (subtype=%s): %s", parsed.get("subtype"), message)
        return {"status": "error", "message": message}

    return {"status": "ok", "result": parsed.get("result", ""), "usage": parsed.get("usage", {})}


async def run_claude(prompt: str) -> dict:
    """Runs `claude` non-interactively against the given prompt, using
    whatever session is already authenticated on this machine -- the same
    one you use interactively, so nothing beyond your normal Claude usage
    gets billed (no API key, no --bare).

    --restricted strips Bash/code-execution/WebFetch and confines any
    remaining file tools to the working directory; running from a fresh,
    empty temp directory (deleted afterward) means there's nothing there
    for those confined file tools to read or usefully write.
    --permission-prompts none denies anything that would otherwise prompt
    for permission, so this never hangs waiting for a human who isn't
    there.

    Returns {"status": "ok", "result": str, "usage": dict} or
    {"status": "error", "message": str}. `usage` is Claude's own token
    accounting, passed through verbatim (input_tokens,
    cache_creation_input_tokens, cache_read_input_tokens, output_tokens).
    """
    work_dir = Path(tempfile.mkdtemp(prefix="claude_cli_"))
    command = [
        "claude", "--print", "--output-format", "json",
        "--max-turns", str(MAX_TURNS), "--max-budget-usd", str(MAX_BUDGET_USD),
        "--restricted", "--permission-prompts", "none",
        prompt,
    ]
    try:
        run_result = await _run_subprocess(command, work_dir, TIMEOUT_SECONDS)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return _parse_claude_output(run_result)

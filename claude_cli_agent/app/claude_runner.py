import asyncio
import json
import shutil
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 300
MAX_TURNS = 1


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
        return {"status": "error", "message": message}

    try:
        parsed = json.loads(run_result["stdout"])
    except ValueError:
        return {"status": "error", "message": "claude CLI returned output that wasn't valid JSON."}

    if parsed.get("is_error"):
        return {"status": "error", "message": parsed.get("result") or "claude CLI reported an error."}

    return {"status": "ok", "result": parsed.get("result", "")}


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

    Returns {"status": "ok", "result": str} or
    {"status": "error", "message": str}.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="claude_cli_"))
    command = [
        "claude", "--print", "--output-format", "json",
        "--max-turns", str(MAX_TURNS), "--restricted", "--permission-prompts", "none",
        prompt,
    ]
    try:
        run_result = await _run_subprocess(command, work_dir, TIMEOUT_SECONDS)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return _parse_claude_output(run_result)

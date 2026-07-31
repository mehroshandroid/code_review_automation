import asyncio
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

BUILD_TIMEOUT_SECONDS = 900
# `xcodebuild -list` triggers full Swift Package Manager dependency
# resolution for any project with SPM packages -- confirmed against a real
# project where most dependencies were cached but one still did a live
# GitHub fetch. A short timeout here was mistaken for "no scheme found."
# Kept well below BUILD_TIMEOUT_SECONDS since resolution should be a
# strict subset of the work the actual build does afterward.
SCHEME_LIST_TIMEOUT_SECONDS = 600


def extract_zip(zip_bytes: bytes, dest_dir: Path) -> None:
    zip_path = dest_dir / "project.zip"
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()


def find_project(project_dir: Path) -> Optional[tuple]:
    """Prefers a .xcworkspace over .xcodeproj (CocoaPods convention: the
    workspace wires in the Pods project alongside the app project, so
    building just the .xcodeproj would miss pod dependencies). Returns
    (path, "-workspace"|"-project"), or None if neither exists."""
    project_dir = Path(project_dir)
    workspaces = list(project_dir.rglob("*.xcworkspace"))
    if workspaces:
        return min(workspaces, key=lambda p: len(p.parts)), "-workspace"
    xcodeprojs = list(project_dir.rglob("*.xcodeproj"))
    if xcodeprojs:
        return min(xcodeprojs, key=lambda p: len(p.parts)), "-project"
    return None


def _parse_scheme_from_list_output(list_output: str) -> Optional[str]:
    if "Schemes:" not in list_output:
        return None
    after_schemes = list_output.split("Schemes:", 1)[1]
    for line in after_schemes.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def discover_scheme(project_path: Path, project_flag: str, derived_data_path: Path) -> Optional[str]:
    """Runs `xcodebuild -list` and returns the first scheme name found.
    Passes -derivedDataPath so the package-graph resolution this triggers
    (see SCHEME_LIST_TIMEOUT_SECONDS) writes its checkouts into our own
    temp directory instead of the user's global Xcode DerivedData."""
    try:
        result = subprocess.run(
            ["xcodebuild", "-list", project_flag, str(project_path), "-derivedDataPath", str(derived_data_path)],
            capture_output=True, text=True, timeout=SCHEME_LIST_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _parse_scheme_from_list_output(result.stdout)


async def _stream_and_collect(stream, label: str) -> str:
    """Reads a subprocess pipe line-by-line, printing each line immediately
    (flushed) so it's visible in real time in the agent's own terminal
    instead of only appearing once the whole build exits, while still
    accumulating the full text to return (mirrors
    compiler/app/lint_runner.py's _stream_and_collect)."""
    lines = []
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip("\n")
        print(f"[xcodebuild {label}] {text}", flush=True)
        lines.append(text)
    return "\n".join(lines)


async def _run_subprocess(command: list, cwd: Path, timeout_seconds: float) -> dict:
    process = await asyncio.create_subprocess_exec(
        *command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout_task = asyncio.create_task(_stream_and_collect(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(_stream_and_collect(process.stderr, "stderr"))
    try:
        await asyncio.wait_for(
            asyncio.gather(process.wait(), stdout_task, stderr_task),
            timeout=timeout_seconds,
        )
        return {
            "returncode": process.returncode,
            "stdout": stdout_task.result(),
            "stderr": stderr_task.result(),
        }
    except asyncio.TimeoutError:
        stdout_task.cancel()
        stderr_task.cancel()
        process.kill()
        await process.wait()
        return {"returncode": None, "stdout": "", "stderr": "xcodebuild process timed out."}


async def run_build(project_dir: Path) -> dict:
    """Builds whichever .xcworkspace/.xcodeproj is found under project_dir
    (see find_project), against its first discovered scheme (see
    discover_scheme), targeting a generic iOS Simulator destination with
    code signing disabled -- no certificates or provisioning profiles are
    ever needed. Build products and resolved Swift Package checkouts are
    written to project_dir/DerivedData rather than the user's global Xcode
    DerivedData, so the caller's existing temp-directory cleanup (removing
    project_dir once the review finishes) catches them automatically --
    nothing accumulates on disk across reviews. Returns {"returncode":
    int|None, "stdout": str, "stderr": str}; the caller decides
    success/failure from the parsed log content, not the exit code (mirrors
    compiler/app/lint_runner.py's run_lint)."""
    found = find_project(project_dir)
    if found is None:
        return {"returncode": None, "stdout": "", "stderr": "No .xcodeproj or .xcworkspace found."}
    project_path, project_flag = found
    derived_data_path = Path(project_dir) / "DerivedData"

    scheme = discover_scheme(project_path, project_flag, derived_data_path)
    if scheme is None:
        return {"returncode": None, "stdout": "", "stderr": "Could not discover a scheme via xcodebuild -list."}

    command = [
        "xcodebuild", "build", project_flag, str(project_path), "-scheme", scheme,
        "-destination", "generic/platform=iOS Simulator",
        "-derivedDataPath", str(derived_data_path),
        "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO",
    ]
    return await _run_subprocess(command, project_path.parent, BUILD_TIMEOUT_SECONDS)

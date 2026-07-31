import asyncio
import zipfile
from pathlib import Path
from typing import Optional

# Generous headroom for a cold-cache NuGet restore + build, same scale as
# Android's GRADLE_TIMEOUT_SECONDS.
BUILD_TIMEOUT_SECONDS = 1440


def extract_zip(zip_bytes: bytes, dest_dir: Path) -> None:
    zip_path = dest_dir / "project.zip"
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()


def find_project(project_dir: Path) -> Optional[Path]:
    """Prefers a .sln (shallowest path) over a standalone .csproj -- mirrors
    dotnet_analyzer.py's find_project_config() precedent from the analysis
    round. The whole discovered solution/project is built with no extra
    module scoping: unlike Android's vendored-library-as-local-project
    problem, NuGet packages are compiled separately and never show up as
    local project files needing exclusion."""
    project_dir = Path(project_dir)
    slns = list(project_dir.rglob("*.sln"))
    if slns:
        return min(slns, key=lambda p: len(p.parts))
    csprojs = list(project_dir.rglob("*.csproj"))
    if csprojs:
        return min(csprojs, key=lambda p: len(p.parts))
    return None


async def _stream_and_collect(stream, label: str) -> str:
    """Reads a subprocess pipe line-by-line, printing each line immediately
    (flushed) so it's visible in real time via `docker compose logs -f`
    instead of only appearing once the whole build exits, while still
    accumulating the full text to return (mirrors
    compiler/app/lint_runner.py's _stream_and_collect)."""
    lines = []
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip("\n")
        print(f"[dotnet build {label}] {text}", flush=True)
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
        return {"returncode": None, "stdout": "", "stderr": "dotnet build process timed out."}


async def run_build(project_dir: Path) -> dict:
    """Runs `dotnet build <path> --nologo -nodeReuse:false
    -p:UseSharedCompilation=false` against whichever .sln/.csproj is found
    under project_dir (see find_project). Both flags are required, not
    optional -- they disable two *separate* background-process mechanisms
    that MSBuild/Roslyn keep alive by default to speed up the next build,
    fine on a single developer machine but not in this container, which
    handles many review requests over its lifetime (it isn't restarted per
    request):
    -nodeReuse:false stops MSBuild's own out-of-process build worker nodes
    from persisting. -p:UseSharedCompilation=false stops Roslyn's separate
    VBCSCompiler shared-compilation server from persisting -- confirmed
    necessary against a real build where, with only -nodeReuse:false set,
    the subprocess's stdout/stderr pipes stayed open (and this function
    stayed blocked) for exactly 10 minutes *after* `dotnet build` had
    already finished and printed its last output line, because a lingering
    VBCSCompiler grandchild process had inherited those pipes and only
    closed them once its own idle-shutdown timer expired.
    Does not raise on a non-zero exit code -- the caller decides
    success/failure from parsed diagnostics, not the exit code, same as
    every other runner this session. Returns
    {"returncode": int|None, "stdout": str, "stderr": str}."""
    project_path = find_project(project_dir)
    if project_path is None:
        return {"returncode": None, "stdout": "", "stderr": "No .sln or .csproj found."}

    command = [
        "dotnet", "build", str(project_path), "--nologo",
        "-nodeReuse:false", "-p:UseSharedCompilation=false",
    ]
    return await _run_subprocess(command, project_path.parent, BUILD_TIMEOUT_SECONDS)

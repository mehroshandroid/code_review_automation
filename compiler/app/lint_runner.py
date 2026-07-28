import zipfile
from pathlib import Path

SDK_DIR = "/opt/android-sdk"
# A cold build (fresh Gradle-distribution download + full dependency
# resolution, now also under amd64/Rosetta emulation on Apple Silicon hosts)
# can legitimately take several minutes for a real project. Leaves headroom
# under the caller's own HTTP timeout (see compile_checker.TIMEOUT_SECONDS).
GRADLE_TIMEOUT_SECONDS = 900


def extract_zip(zip_bytes: bytes, dest_dir: Path) -> None:
    zip_path = dest_dir / "project.zip"
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()


def find_gradle_root(project_dir: Path) -> Path:
    """Real-world project zips commonly wrap everything in one top-level
    directory (a GitHub zip download, or a manually zipped project folder),
    so the actual Gradle project root is wherever settings.gradle(.kts)
    actually lives, not necessarily the top of the extracted archive. Falls
    back to a build.gradle(.kts) location for single-module projects with
    no settings file, and finally to project_dir itself.
    """
    project_dir = Path(project_dir)
    for name in ("settings.gradle.kts", "settings.gradle"):
        for path in project_dir.rglob(name):
            return path.parent
    for name in ("build.gradle.kts", "build.gradle"):
        for path in project_dir.rglob(name):
            return path.parent
    return project_dir


async def _stream_and_collect(stream, label: str) -> str:
    """Reads a subprocess pipe line-by-line, printing each line immediately
    (flushed) so it's visible in real time via `docker compose logs -f` /
    Docker Desktop instead of only appearing once the whole process exits,
    while still accumulating the full text to return.
    """
    lines = []
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip("\n")
        print(f"[gradlew {label}] {text}", flush=True)
        lines.append(text)
    return "\n".join(lines)


async def _run_subprocess_streaming(command: list, cwd: Path, timeout_seconds: float) -> dict:
    import asyncio

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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
        return {"returncode": None, "stdout": "", "stderr": "Gradle process timed out."}


async def run_lint(project_dir: Path) -> dict:
    """Runs `sh ./gradlew lint` (or the preinstalled fallback Gradle if no
    wrapper is present) inside the discovered Gradle root under project_dir
    (see find_gradle_root). Does not raise on a non-zero exit code --
    Android Lint's own Gradle task exits non-zero whenever there's an
    Error-severity finding, which is not the same as the build failing to
    compile; the caller decides success/failure by checking whether a lint
    report was produced, not the exit code.

    Returns {"returncode": int|None, "stdout": str, "stderr": str} -- the
    caller surfaces this so a build failure is diagnosable instead of being
    a silent dead end. Output streams to this process's own stdout in real
    time as the build runs (see _stream_and_collect).
    """
    gradle_root = find_gradle_root(project_dir)
    (gradle_root / "local.properties").write_text(f"sdk.dir={SDK_DIR}\n")

    gradlew = gradle_root / "gradlew"
    command = ["sh", "gradlew", "lint"] if gradlew.exists() else ["gradle", "lint"]

    return await _run_subprocess_streaming(command, gradle_root, GRADLE_TIMEOUT_SECONDS)

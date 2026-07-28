import zipfile
from pathlib import Path

SDK_DIR = "/opt/android-sdk"
GRADLE_TIMEOUT_SECONDS = 280  # leaves headroom under the caller's 5-minute HTTP timeout


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
    a silent dead end.
    """
    import asyncio

    gradle_root = find_gradle_root(project_dir)
    (gradle_root / "local.properties").write_text(f"sdk.dir={SDK_DIR}\n")

    gradlew = gradle_root / "gradlew"
    command = ["sh", "gradlew", "lint"] if gradlew.exists() else ["gradle", "lint"]

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=gradle_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=GRADLE_TIMEOUT_SECONDS)
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {"returncode": None, "stdout": "", "stderr": "Gradle process timed out."}

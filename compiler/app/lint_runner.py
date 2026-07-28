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


async def run_lint(project_dir: Path) -> None:
    """Runs `sh ./gradlew lint` (or the preinstalled fallback Gradle if no
    wrapper is present) inside project_dir. Does not raise on a non-zero
    exit code -- Android Lint's own Gradle task exits non-zero whenever
    there's an Error-severity finding, which is not the same as the build
    failing to compile; the caller decides success/failure by checking
    whether a lint report was produced, not the exit code.
    """
    import asyncio

    (project_dir / "local.properties").write_text(f"sdk.dir={SDK_DIR}\n")

    gradlew = project_dir / "gradlew"
    command = ["sh", "gradlew", "lint"] if gradlew.exists() else ["gradle", "lint"]

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(process.communicate(), timeout=GRADLE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()

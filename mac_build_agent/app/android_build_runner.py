import os
from pathlib import Path
from typing import Optional

from app.build_runner import _run_subprocess

_APPLICATION_PLUGIN_ID = "com.android.application"
# A cold build (fresh Gradle-distribution download + full dependency
# resolution) can legitimately take several minutes for a real project.
GRADLE_TIMEOUT_SECONDS = 1440


def _resolve_sdk_dir() -> str:
    """Docker's compiler service hardcodes /opt/android-sdk (baked into its
    own Dockerfile); on a host Mac there's no such fixed path, so this
    checks the standard Android tooling env vars first (whatever the user's
    own Android Studio/shell setup already exports), then falls back to the
    conventional per-user install location."""
    return (
        os.environ.get("ANDROID_HOME")
        or os.environ.get("ANDROID_SDK_ROOT")
        or str(Path.home() / "Library" / "Android" / "sdk")
    )


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


def _resolve_version_catalog_alias(gradle_root: Path) -> Optional[str]:
    """Modern projects often apply plugins via a version-catalog alias
    (e.g. `alias(libs.plugins.android.application)`) rather than the
    literal plugin id string -- the id only appears in
    gradle/libs.versions.toml. Looks up that file's [plugins] table for
    whichever alias maps to com.android.application, and returns the
    dotted accessor form Gradle generates for it (e.g. the TOML key
    "android-application" becomes "libs.plugins.android.application").
    """
    catalog_path = gradle_root / "gradle" / "libs.versions.toml"
    if not catalog_path.exists():
        return None
    try:
        content = catalog_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    in_plugins_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_plugins_section = stripped == "[plugins]"
            continue
        if not in_plugins_section or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if f'"{_APPLICATION_PLUGIN_ID}"' in value or f"'{_APPLICATION_PLUGIN_ID}'" in value:
            alias = key.strip().strip('"').strip("'")
            return "libs.plugins." + alias.replace("-", ".").replace("_", ".")
    return None


def _module_applies_android_application(build_file: Path, catalog_alias: Optional[str]) -> bool:
    try:
        content = build_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    if _APPLICATION_PLUGIN_ID in content:
        return True
    if catalog_alias and catalog_alias in content:
        return True
    return False


def find_app_module_path(gradle_root: Path) -> Optional[str]:
    """Locates whichever module applies the com.android.application plugin
    -- the actual Android application module, as opposed to library
    modules (third-party/vendored dependencies included as local project
    modules), so lint can be scoped to just that one module instead of
    every module in the project. Returns a Gradle project path like
    ":app", or None if no match was found (caller falls back to the
    unscoped aggregate lint task).
    """
    gradle_root = Path(gradle_root)
    catalog_alias = _resolve_version_catalog_alias(gradle_root)
    for name in ("build.gradle.kts", "build.gradle"):
        for build_file in gradle_root.rglob(name):
            if build_file.parent == gradle_root:
                continue  # the root project's own build file is never a module
            if _module_applies_android_application(build_file, catalog_alias):
                relative = build_file.parent.relative_to(gradle_root)
                return ":" + ":".join(relative.parts)
    return None


async def run_lint(project_dir: Path) -> dict:
    """Runs `sh ./gradlew :app:lint` -- scoped to whichever module applies
    com.android.application (see find_app_module_path) -- or the
    preinstalled fallback Gradle if no wrapper is present. Falls back to
    the unscoped aggregate `lint` task if no application module could be
    identified. Runs inside the discovered Gradle root under project_dir
    (see find_gradle_root). Does not raise on a non-zero exit code --
    Android Lint's own Gradle task exits non-zero whenever there's an
    Error-severity finding, which is not the same as the build failing to
    compile; the caller decides success/failure by checking whether a lint
    report was produced, not the exit code.

    Reuses app.build_runner's streaming subprocess runner (_run_subprocess)
    -- the same one iOS's xcodebuild invocation uses -- so build output
    streams live here too, and inherits its timeout-handling behavior.
    """
    gradle_root = find_gradle_root(project_dir)
    (gradle_root / "local.properties").write_text(f"sdk.dir={_resolve_sdk_dir()}\n")

    gradlew = gradle_root / "gradlew"
    base_command = ["sh", "gradlew"] if gradlew.exists() else ["gradle"]

    app_module = find_app_module_path(gradle_root)
    lint_task = f"{app_module}:lint" if app_module else "lint"

    return await _run_subprocess(base_command + [lint_task], gradle_root, GRADLE_TIMEOUT_SECONDS)

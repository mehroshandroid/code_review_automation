import pytest

from app.lint_runner import _run_subprocess_streaming, find_app_module_path, find_gradle_root


@pytest.mark.asyncio
async def test_run_subprocess_streaming_collects_full_stdout_and_stderr(tmp_path):
    result = await _run_subprocess_streaming(
        ["sh", "-c", "echo out-line-1; echo out-line-2; echo err-line-1 1>&2"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert result["returncode"] == 0
    assert result["stdout"] == "out-line-1\nout-line-2"
    assert result["stderr"] == "err-line-1"


@pytest.mark.asyncio
async def test_run_subprocess_streaming_reports_nonzero_exit_code(tmp_path):
    result = await _run_subprocess_streaming(["sh", "-c", "exit 3"], cwd=tmp_path, timeout_seconds=10)
    assert result["returncode"] == 3


@pytest.mark.asyncio
async def test_run_subprocess_streaming_times_out(tmp_path):
    result = await _run_subprocess_streaming(["sh", "-c", "sleep 5"], cwd=tmp_path, timeout_seconds=0.2)
    assert result == {"returncode": None, "stdout": "", "stderr": "Gradle process timed out."}


def test_find_gradle_root_locates_a_nested_settings_gradle_kts(tmp_path):
    # Mirrors a common real-world shape: the zip wraps everything in one
    # top-level folder (e.g. a GitHub zip download or a manually zipped
    # project directory), so the actual Gradle root is one level below the
    # extraction root, not the extraction root itself.
    project_root = tmp_path / "MyProject"
    project_root.mkdir()
    (project_root / "settings.gradle.kts").write_text("")
    (project_root / "gradlew").write_text("#!/bin/sh")

    assert find_gradle_root(tmp_path) == project_root


def test_find_gradle_root_locates_a_nested_settings_gradle(tmp_path):
    project_root = tmp_path / "MyProject"
    project_root.mkdir()
    (project_root / "settings.gradle").write_text("")

    assert find_gradle_root(tmp_path) == project_root


def test_find_gradle_root_falls_back_to_build_gradle_when_no_settings_file(tmp_path):
    project_root = tmp_path / "MyProject"
    project_root.mkdir()
    (project_root / "build.gradle").write_text("")

    assert find_gradle_root(tmp_path) == project_root


def test_find_gradle_root_falls_back_to_the_extraction_root_when_nothing_found(tmp_path):
    assert find_gradle_root(tmp_path) == tmp_path


def test_find_app_module_path_via_groovy_apply_plugin_syntax(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("apply plugin: 'com.android.application'\n")

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_via_kotlin_dsl_plugins_block(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle.kts").write_text('plugins {\n    id("com.android.application")\n}\n')

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_skips_library_modules(tmp_path):
    # A third-party/vendored library module (com.android.library) sitting
    # alongside the real app module must never be mistaken for it, since
    # the whole point is scoping lint away from modules like this one.
    lib_dir = tmp_path / "countrycodepicker"
    lib_dir.mkdir()
    (lib_dir / "build.gradle").write_text("apply plugin: 'com.android.library'\n")

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("apply plugin: 'com.android.application'\n")

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_resolves_a_version_catalog_alias(tmp_path):
    # Modern projects commonly apply plugins via a version-catalog alias
    # (alias(libs.plugins.android.application)) instead of the literal
    # plugin id string -- the id only appears in gradle/libs.versions.toml.
    catalog_dir = tmp_path / "gradle"
    catalog_dir.mkdir()
    (catalog_dir / "libs.versions.toml").write_text(
        '[plugins]\n'
        'android-application = { id = "com.android.application", version.ref = "agp" }\n'
    )
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle.kts").write_text(
        'plugins {\n    alias(libs.plugins.android.application)\n}\n'
    )

    assert find_app_module_path(tmp_path) == ":app"


def test_find_app_module_path_returns_none_when_no_application_module_found(tmp_path):
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()
    (lib_dir / "build.gradle").write_text("apply plugin: 'com.android.library'\n")

    assert find_app_module_path(tmp_path) is None

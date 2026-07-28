from app.lint_runner import find_gradle_root


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

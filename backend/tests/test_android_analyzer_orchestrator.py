from pathlib import Path

from app.analyzer.android_analyzer import analyze_project


def _build_minimal_project(tmp_path: Path) -> Path:
    (tmp_path / "build.gradle").write_text(
        "android { compileSdkVersion 30\n defaultConfig { targetSdkVersion 30 } }\n"
        "dependencies { implementation 'androidx.core:core-ktx:1.9.0' }\n"
    )
    (tmp_path / "AndroidManifest.xml").write_text("<manifest />")
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Constants.java").write_text(
        'class Constants { static final String API_KEY = "ab12cd34ef56gh78ij90kl12mn34op56"; }'
    )
    return tmp_path


def test_analyze_project_aggregates_all_findings(tmp_path: Path):
    project_dir = _build_minimal_project(tmp_path)
    result = analyze_project(project_dir)

    assert result.fatal_error is None
    assert result.build_info["compile_sdk"] == 30
    assert result.source_stats["java_count"] == 1
    assert result.test_coverage is None
    assert any("compileSdkVersion 30" in w["issue"] for w in result.version_warnings)
    assert any(f["pattern"] == "api_key" for f in result.secrets_found)


def test_analyze_project_fatal_error_when_no_source(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("android {}")
    result = analyze_project(tmp_path)
    assert result.fatal_error == "No source files found (.java/.kt)"


def test_analyze_project_handles_directory_named_build_gradle(tmp_path: Path):
    """Test that a directory literally named build.gradle doesn't crash analyze_project."""
    # Create a directory named build.gradle (will be found by rglob but can't be read as a file)
    (tmp_path / "build.gradle").mkdir()
    # Add required files
    (tmp_path / "AndroidManifest.xml").write_text("<manifest />")
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Main.java").write_text("class Main {}")

    # This should not raise IsADirectoryError; should degrade gracefully
    result = analyze_project(tmp_path)

    # Should complete without error
    assert result is not None
    assert result.fatal_error is None
    # build_info should have empty values since the gradle_content was empty
    assert result.build_info["compile_sdk"] is None
    assert result.build_info["target_sdk"] is None
    assert result.build_info["gradle_version"] is None
    assert result.build_info["kotlin_version"] is None
    assert result.build_info["dependencies"] == []

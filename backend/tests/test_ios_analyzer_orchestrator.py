from pathlib import Path

from app.analyzer.ios_analyzer import analyze_project


def _build_minimal_project(tmp_path: Path) -> Path:
    xcodeproj = tmp_path / "MyApp.xcodeproj"
    xcodeproj.mkdir()
    (xcodeproj / "project.pbxproj").write_text(
        "buildSettings = { IPHONEOS_DEPLOYMENT_TARGET = 14.0; SWIFT_VERSION = 5.5; };"
    )
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Constants.swift").write_text(
        'let apiKey = "ab12cd34ef56gh78ij90kl12mn34op56"'
    )
    return tmp_path


def test_analyze_project_aggregates_all_findings(tmp_path: Path):
    project_dir = _build_minimal_project(tmp_path)
    result = analyze_project(project_dir)

    assert result.fatal_error is None
    assert result.build_info["deployment_target"] == "14.0"
    assert result.source_stats["swift_count"] == 1
    assert result.test_coverage is None
    assert any("deployment target 14.0" in w["issue"] for w in result.version_warnings)
    assert any(f["pattern"] == "api_key" for f in result.secrets_found)


def test_analyze_project_fatal_error_when_no_source(tmp_path: Path):
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    result = analyze_project(tmp_path)
    assert result.fatal_error == "No source files found (.swift/.m/.mm)"


def test_analyze_project_gracefully_degrades_with_no_pbxproj(tmp_path: Path):
    """A pure Swift Package Manager project (no project.pbxproj) must not crash --
    it just gets zero version warnings, same as Android's missing-build.gradle fallback."""
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9")
    src = tmp_path / "Sources"
    src.mkdir()
    (src / "Lib.swift").write_text("struct Lib {}")

    result = analyze_project(tmp_path)

    assert result.fatal_error is None
    assert result.build_info["deployment_target"] is None
    assert result.build_info["swift_version"] is None
    assert result.version_warnings == []

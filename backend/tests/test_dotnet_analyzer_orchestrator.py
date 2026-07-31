from pathlib import Path

from app.analyzer.dotnet_analyzer import analyze_project


def _build_minimal_project(tmp_path: Path) -> Path:
    (tmp_path / "MyApp.sln").write_text("stub")
    app_dir = tmp_path / "MyApp"
    app_dir.mkdir()
    (app_dir / "MyApp.csproj").write_text(
        "<Project><PropertyGroup><TargetFramework>net6.0</TargetFramework></PropertyGroup></Project>"
    )
    (app_dir / "Constants.cs").write_text(
        'public const string ApiKey = "ab12cd34ef56gh78ij90kl12mn34op56";'
    )
    return tmp_path


def test_analyze_project_aggregates_all_findings(tmp_path: Path):
    project_dir = _build_minimal_project(tmp_path)
    result = analyze_project(project_dir)

    assert result.fatal_error is None
    assert result.build_info["target_framework"] == "net6.0"
    assert result.source_stats["cs_count"] == 1
    assert result.test_coverage is None
    assert any("net6.0" in w["issue"] for w in result.version_warnings)
    assert any(f["pattern"] == "api_key" for f in result.secrets_found)


def test_analyze_project_fatal_error_when_no_source(tmp_path: Path):
    (tmp_path / "MyApp.sln").write_text("stub")
    result = analyze_project(tmp_path)
    assert result.fatal_error == "No source files found (.cs)"


def test_analyze_project_gracefully_degrades_with_no_project_file(tmp_path: Path):
    """No .sln/.csproj at all must not crash -- zero version warnings, same
    graceful fallback Android/iOS already have for a missing build config."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "Program.cs").write_text("class Program {}")

    result = analyze_project(tmp_path)

    assert result.fatal_error is None
    assert result.build_info["target_framework"] is None
    assert result.version_warnings == []

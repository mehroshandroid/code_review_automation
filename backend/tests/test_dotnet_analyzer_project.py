from pathlib import Path

from app.analyzer.dotnet_analyzer import find_project_config, parse_dotnet_project, validate_project_structure

CSPROJ_CONTENT = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>
"""


def test_parse_dotnet_project_extracts_target_framework():
    info = parse_dotnet_project(CSPROJ_CONTENT)
    assert info["target_framework"] == "net8.0"


def test_parse_dotnet_project_extracts_legacy_target_framework_version():
    info = parse_dotnet_project(
        "<Project><PropertyGroup><TargetFrameworkVersion>v4.8</TargetFrameworkVersion></PropertyGroup></Project>"
    )
    assert info["target_framework"] == "v4.8"


def test_parse_dotnet_project_missing_field_is_none():
    info = parse_dotnet_project("<Project><PropertyGroup></PropertyGroup></Project>")
    assert info["target_framework"] is None


def test_find_project_config_locates_a_csproj(tmp_path: Path):
    app_dir = tmp_path / "src" / "MyApp"
    app_dir.mkdir(parents=True)
    (app_dir / "MyApp.csproj").write_text(CSPROJ_CONTENT)

    found = find_project_config(tmp_path)
    assert found == app_dir / "MyApp.csproj"


def test_find_project_config_returns_none_when_absent(tmp_path: Path):
    assert find_project_config(tmp_path) is None


def test_validate_project_structure_happy_path(tmp_path: Path):
    (tmp_path / "MyApp.sln").write_text("Microsoft Visual Studio Solution File")
    app_dir = tmp_path / "MyApp"
    app_dir.mkdir()
    (app_dir / "MyApp.csproj").write_text(CSPROJ_CONTENT)
    (app_dir / "Program.cs").write_text("class Program {}")

    result = validate_project_structure(tmp_path)
    assert result["warnings"] == []
    assert result["fatal_error"] is None


def test_validate_project_structure_accepts_a_standalone_csproj_without_a_sln(tmp_path: Path):
    (tmp_path / "MyApp.csproj").write_text(CSPROJ_CONTENT)
    (tmp_path / "Program.cs").write_text("class Program {}")

    result = validate_project_structure(tmp_path)
    assert "Missing .sln or .csproj" not in result["warnings"]


def test_validate_project_structure_flags_missing_project_file_non_fatally(tmp_path: Path):
    (tmp_path / "Program.cs").write_text("class Program {}")

    result = validate_project_structure(tmp_path)
    assert "Missing .sln or .csproj" in result["warnings"]
    assert result["fatal_error"] is None


def test_validate_project_structure_fatal_when_no_source(tmp_path: Path):
    (tmp_path / "MyApp.sln").write_text("stub")
    result = validate_project_structure(tmp_path)
    assert result["fatal_error"] == "No source files found (.cs)"

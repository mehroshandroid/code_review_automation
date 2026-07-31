from pathlib import Path

from app.analyzer.ios_analyzer import find_project_config, parse_xcode_project, validate_project_structure

PBXPROJ_CONTENT = """// !$*UTF8*$!
{
	archiveVersion = 1;
	objects = {
		ABC123 /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				IPHONEOS_DEPLOYMENT_TARGET = 15.0;
				SWIFT_VERSION = 5.0;
			};
			name = Debug;
		};
	};
}
"""


def test_parse_xcode_project_extracts_deployment_target_and_swift_version():
    info = parse_xcode_project(PBXPROJ_CONTENT)
    assert info["deployment_target"] == "15.0"
    assert info["swift_version"] == "5.0"


def test_parse_xcode_project_missing_fields_are_none():
    info = parse_xcode_project("{ archiveVersion = 1; }\n")
    assert info["deployment_target"] is None
    assert info["swift_version"] is None


def test_find_project_config_prefers_the_app_xcodeproj_over_a_nested_dependency(tmp_path: Path):
    pods_dir = tmp_path / "Pods" / "SomeDependency.xcodeproj"
    pods_dir.mkdir(parents=True)
    (pods_dir / "project.pbxproj").write_text("// dependency project")

    app_dir = tmp_path / "MyApp.xcodeproj"
    app_dir.mkdir()
    (app_dir / "project.pbxproj").write_text(PBXPROJ_CONTENT)

    found = find_project_config(tmp_path)
    assert found == app_dir / "project.pbxproj"


def test_find_project_config_returns_none_when_absent(tmp_path: Path):
    assert find_project_config(tmp_path) is None


def test_validate_project_structure_happy_path(tmp_path: Path):
    xcodeproj = tmp_path / "MyApp.xcodeproj"
    xcodeproj.mkdir()
    (xcodeproj / "project.pbxproj").write_text(PBXPROJ_CONTENT)
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")

    result = validate_project_structure(tmp_path)
    assert result["warnings"] == []
    assert result["fatal_error"] is None


def test_validate_project_structure_flags_missing_files_non_fatally(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")

    result = validate_project_structure(tmp_path)
    assert "Missing Xcode project (.xcodeproj/.xcworkspace) or Package.swift" in result["warnings"]
    assert "Missing Info.plist" in result["warnings"]
    assert result["fatal_error"] is None


def test_validate_project_structure_accepts_package_swift_as_a_project_file(tmp_path: Path):
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9")
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    src = tmp_path / "Sources"
    src.mkdir()
    (src / "Lib.swift").write_text("struct Lib {}")

    result = validate_project_structure(tmp_path)
    assert "Missing Xcode project (.xcodeproj/.xcworkspace) or Package.swift" not in result["warnings"]


def test_validate_project_structure_fatal_when_no_source(tmp_path: Path):
    (tmp_path / "Info.plist").write_text("<plist></plist>")
    result = validate_project_structure(tmp_path)
    assert result["fatal_error"] == "No source files found (.swift/.m/.mm)"

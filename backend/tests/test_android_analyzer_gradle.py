from pathlib import Path

from app.analyzer.android_analyzer import find_gradle_file, parse_gradle, validate_project_structure

GROOVY_GRADLE = """
buildscript {
    ext.kotlin_version = '1.6.0'
    dependencies {
        classpath 'com.android.tools.build:gradle:7.0.0'
    }
}
apply plugin: 'jacoco'
android {
    compileSdkVersion 30
    defaultConfig {
        targetSdkVersion 30
    }
}
dependencies {
    implementation 'androidx.core:core-ktx:1.9.0'
    testImplementation 'junit:junit:4.13.2'
}
"""

KOTLIN_DSL_GRADLE = """
plugins {
    id("com.android.application") version "8.1.0"
    id("org.jetbrains.kotlin.android") version "1.9.0"
}
android {
    compileSdk = 34
    defaultConfig {
        targetSdk = 34
    }
}
dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
}
"""


def test_parse_groovy_gradle():
    info = parse_gradle(GROOVY_GRADLE)
    assert info["compile_sdk"] == 30
    assert info["target_sdk"] == 30
    assert info["gradle_version"] == "7.0.0"
    assert info["kotlin_version"] == "1.6.0"
    assert "androidx.core:core-ktx:1.9.0" in info["dependencies"]
    assert info["has_jacoco"] is True
    assert info["has_kover"] is False


def test_parse_kotlin_dsl_gradle():
    info = parse_gradle(KOTLIN_DSL_GRADLE)
    assert info["compile_sdk"] == 34
    assert info["target_sdk"] == 34
    assert info["gradle_version"] == "8.1.0"
    assert info["kotlin_version"] == "1.9.0"
    assert info["has_jacoco"] is False


def test_parse_gradle_missing_fields_are_none():
    info = parse_gradle("android {}\n")
    assert info["compile_sdk"] is None
    assert info["gradle_version"] is None
    assert info["dependencies"] == []


def test_find_gradle_file_prefers_app_module(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("// root")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("android {}")
    found = find_gradle_file(tmp_path)
    assert found == app_dir / "build.gradle"


def test_validate_project_structure_happy_path(tmp_path: Path):
    (tmp_path / "build.gradle").write_text(GROOVY_GRADLE)
    (tmp_path / "AndroidManifest.xml").write_text("<manifest />")
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Main.java").write_text("class Main {}")
    result = validate_project_structure(tmp_path)
    assert result["warnings"] == []
    assert result["fatal_error"] is None


def test_validate_project_structure_flags_missing_files_non_fatally(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Main.java").write_text("class Main {}")
    result = validate_project_structure(tmp_path)
    assert "Missing build.gradle" in result["warnings"]
    assert "Missing AndroidManifest.xml" in result["warnings"]
    assert result["fatal_error"] is None


def test_validate_project_structure_fatal_when_no_source(tmp_path: Path):
    (tmp_path / "build.gradle").write_text(GROOVY_GRADLE)
    result = validate_project_structure(tmp_path)
    assert result["fatal_error"] == "No source files found (.java/.kt)"

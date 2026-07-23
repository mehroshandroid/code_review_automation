from pathlib import Path

from app.analyzer.android_analyzer import count_source_files, detect_test_coverage

JACOCO_REPORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="INSTRUCTION" missed="20" covered="80"/>
    <counter type="LINE" missed="10" covered="40"/>
</report>
"""


def test_count_source_files_counts_and_flags_tests(tmp_path: Path):
    main_dir = tmp_path / "src" / "main" / "java"
    main_dir.mkdir(parents=True)
    (main_dir / "MainActivity.java").write_text("class MainActivity {}")
    (main_dir / "Util.kt").write_text("class Util")
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "MainActivityTest.java").write_text("class MainActivityTest {}")

    stats = count_source_files(tmp_path)
    assert stats["java_count"] == 2
    assert stats["kotlin_count"] == 1
    assert stats["test_file_count"] == 1


def test_detect_test_coverage_returns_none_without_jacoco_or_kover(tmp_path: Path):
    gradle_info = {"has_jacoco": False, "has_kover": False}
    assert detect_test_coverage(tmp_path, gradle_info) is None


def test_detect_test_coverage_parses_jacoco_report(tmp_path: Path):
    report_dir = tmp_path / "build" / "reports" / "jacoco"
    report_dir.mkdir(parents=True)
    (report_dir / "jacocoTestReport.xml").write_text(JACOCO_REPORT_XML)
    gradle_info = {"has_jacoco": True, "has_kover": False}
    coverage = detect_test_coverage(tmp_path, gradle_info)
    assert coverage == 80.0


def test_detect_test_coverage_none_when_report_missing(tmp_path: Path):
    gradle_info = {"has_jacoco": True, "has_kover": False}
    assert detect_test_coverage(tmp_path, gradle_info) is None


def test_detect_test_coverage_handles_malformed_xml(tmp_path: Path):
    report_dir = tmp_path / "build" / "reports" / "jacoco"
    report_dir.mkdir(parents=True)
    (report_dir / "jacocoTestReport.xml").write_text("<truncated>")
    gradle_info = {"has_jacoco": True, "has_kover": False}
    coverage = detect_test_coverage(tmp_path, gradle_info)
    assert coverage is None

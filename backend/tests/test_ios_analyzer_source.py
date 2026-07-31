from pathlib import Path

from app.analyzer.ios_analyzer import count_source_files, detect_test_coverage

LCOV_REPORT = """TN:
SF:/project/Sources/File.swift
DA:1,1
DA:2,0
DA:3,1
LF:3
LH:2
end_of_record
SF:/project/Sources/Other.swift
DA:1,1
DA:2,1
LF:2
LH:2
end_of_record
"""


def test_count_source_files_counts_and_flags_tests(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")
    (src / "Legacy.m").write_text("@implementation Legacy @end")
    test_dir = tmp_path / "MyAppTests"
    test_dir.mkdir()
    (test_dir / "AppDelegateTests.swift").write_text("class AppDelegateTests {}")

    stats = count_source_files(tmp_path)
    assert stats["swift_count"] == 2
    assert stats["objc_count"] == 1
    assert stats["test_file_count"] == 1


def test_detect_test_coverage_returns_none_without_a_report(tmp_path: Path):
    assert detect_test_coverage(tmp_path) is None


def test_detect_test_coverage_parses_lcov_report(tmp_path: Path):
    (tmp_path / "lcov.info").write_text(LCOV_REPORT)
    coverage = detect_test_coverage(tmp_path)
    assert coverage == 80.0


def test_detect_test_coverage_ignores_unrelated_info_files(tmp_path: Path):
    (tmp_path / "notes.info").write_text("just some unrelated notes\n")
    assert detect_test_coverage(tmp_path) is None

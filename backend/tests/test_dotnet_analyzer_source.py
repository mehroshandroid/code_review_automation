from pathlib import Path

from app.analyzer.dotnet_analyzer import count_source_files, detect_test_coverage

COBERTURA_REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<coverage line-rate="0.85" branch-rate="0.7" version="1.9">
    <packages></packages>
</coverage>
"""


def test_count_source_files_counts_and_flags_tests(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Program.cs").write_text("class Program {}")
    (src / "PaymentService.cs").write_text("class PaymentService {}")
    test_dir = tmp_path / "MyApp.Tests"
    test_dir.mkdir()
    (test_dir / "PaymentServiceTests.cs").write_text("class PaymentServiceTests {}")

    stats = count_source_files(tmp_path)
    assert stats["cs_count"] == 3
    assert stats["test_file_count"] == 1


def test_detect_test_coverage_returns_none_without_a_report(tmp_path: Path):
    assert detect_test_coverage(tmp_path) is None


def test_detect_test_coverage_parses_cobertura_report(tmp_path: Path):
    (tmp_path / "coverage.cobertura.xml").write_text(COBERTURA_REPORT)
    coverage = detect_test_coverage(tmp_path)
    assert coverage == 85.0


def test_detect_test_coverage_handles_malformed_xml(tmp_path: Path):
    (tmp_path / "coverage.cobertura.xml").write_text("<truncated>")
    assert detect_test_coverage(tmp_path) is None

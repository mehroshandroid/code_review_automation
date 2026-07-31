from pathlib import Path

from app.analyzer.dotnet_analyzer import gather_code_context


def test_gather_code_context_includes_file_headers_and_content(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Program.cs").write_text("class Program {}")

    context = gather_code_context(tmp_path)
    assert "Program.cs" in context
    assert "class Program {}" in context


def test_gather_code_context_returns_empty_string_when_no_source(tmp_path: Path):
    assert gather_code_context(tmp_path) == ""


def test_gather_code_context_respects_max_chars_budget(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Big.cs").write_text("x" * 1000)
    (src / "AlsoBig.cs").write_text("y" * 1000)
    context = gather_code_context(tmp_path, max_chars=500)
    assert len(context) <= 500 + 200
    assert "y" * 1000 not in context

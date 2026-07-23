from pathlib import Path

from app.analyzer.android_analyzer import gather_code_context


def test_gather_code_context_includes_file_headers_and_content(tmp_path: Path):
    src = tmp_path / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)
    (src / "MainActivity.java").write_text("class MainActivity {}")
    context = gather_code_context(tmp_path)
    assert "MainActivity.java" in context
    assert "class MainActivity {}" in context


def test_gather_code_context_returns_empty_string_when_no_source(tmp_path: Path):
    assert gather_code_context(tmp_path) == ""


def test_gather_code_context_respects_max_chars_budget(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Big.java").write_text("x" * 1000)
    (src / "AlsoBig.java").write_text("y" * 1000)
    context = gather_code_context(tmp_path, max_chars=500)
    assert len(context) <= 500 + 200  # headers add some overhead; budget is approximate, not exceeded by a full extra file
    assert "y" * 1000 not in context  # second file never fully included once budget is exhausted


def test_gather_code_context_is_deterministic(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Zebra.java").write_text("// zebra")
    (src / "Apple.java").write_text("// apple")
    context1 = gather_code_context(tmp_path)
    context2 = gather_code_context(tmp_path)
    assert context1 == context2
    assert context1.index("Apple.java") < context1.index("Zebra.java")

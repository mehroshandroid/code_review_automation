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


def test_gather_code_context_prioritizes_program_cs_over_alphabetically_earlier_files(tmp_path: Path):
    # "AController.cs" sorts before "Program.cs" alphabetically, but
    # Program.cs is where JWT auth configuration actually lives -- it must
    # win the budget regardless of alphabetical position.
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AController.cs").write_text("x" * 400)
    (src / "Program.cs").write_text("y" * 400)

    context = gather_code_context(tmp_path, max_chars=500)
    assert "y" * 400 in context
    assert "x" * 400 not in context


def test_gather_code_context_prioritizes_startup_cs_over_alphabetically_earlier_files(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AController.cs").write_text("x" * 400)
    (src / "Startup.cs").write_text("y" * 400)

    context = gather_code_context(tmp_path, max_chars=500)
    assert "y" * 400 in context
    assert "x" * 400 not in context


def test_gather_code_context_prioritizes_controllers_over_alphabetically_earlier_non_controller_files(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AEarlyFile.cs").write_text("x" * 400)
    (src / "OrderController.cs").write_text("y" * 400)

    context = gather_code_context(tmp_path, max_chars=500)
    assert "y" * 400 in context
    assert "x" * 400 not in context


def test_gather_code_context_falls_back_to_alphabetical_order_within_the_controllers_tier(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "ZController.cs").write_text("z" * 400)
    (src / "AController.cs").write_text("a" * 400)

    context = gather_code_context(tmp_path, max_chars=500)
    assert "a" * 400 in context
    assert "z" * 400 not in context


def test_gather_code_context_falls_back_to_alphabetical_order_for_non_priority_files(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "ZService.cs").write_text("z" * 400)
    (src / "AService.cs").write_text("a" * 400)

    context = gather_code_context(tmp_path, max_chars=500)
    assert "a" * 400 in context
    assert "z" * 400 not in context

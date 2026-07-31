from pathlib import Path

from app.analyzer.ios_analyzer import gather_code_context


def test_gather_code_context_includes_swift_objc_and_header_content(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "AppDelegate.swift").write_text("class AppDelegate {}")
    (src / "Legacy.m").write_text("@implementation Legacy @end")
    (src / "Legacy.h").write_text("@interface Legacy : NSObject @end")

    context = gather_code_context(tmp_path)
    assert "AppDelegate.swift" in context
    assert "class AppDelegate {}" in context
    assert "@implementation Legacy @end" in context
    assert "@interface Legacy : NSObject @end" in context


def test_gather_code_context_returns_empty_string_when_no_source(tmp_path: Path):
    assert gather_code_context(tmp_path) == ""


def test_gather_code_context_respects_max_chars_budget(tmp_path: Path):
    src = tmp_path / "MyApp"
    src.mkdir()
    (src / "Big.swift").write_text("x" * 1000)
    (src / "AlsoBig.swift").write_text("y" * 1000)
    context = gather_code_context(tmp_path, max_chars=500)
    assert len(context) <= 500 + 200
    assert "y" * 1000 not in context

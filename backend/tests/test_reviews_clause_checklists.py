import io
import tempfile
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

import app.api.reviews as reviews_module
from app.api.reviews import _load_clause_checklists, _new_review_state, _reviews, _run_review


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _FakeChecklist:
    def __init__(self, platform, sub_id, checklist_text):
        self.platform = platform
        self.sub_id = sub_id
        self.checklist_text = checklist_text


async def test_load_clause_checklists_builds_a_dict_keyed_by_platform_and_sub_id(monkeypatch):
    async def fake_list_clause_checklists(session):
        return [_FakeChecklist(".NET", "2.4", "Check JWT config"), _FakeChecklist("Android", "2.3", "Check secrets")]

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "list_clause_checklists", fake_list_clause_checklists)

    checklists = await _load_clause_checklists()

    assert checklists == {
        (".NET", "2.4"): "Check JWT config",
        ("Android", "2.3"): "Check secrets",
    }


async def test_load_clause_checklists_returns_empty_dict_on_db_failure(monkeypatch):
    async def fake_list_clause_checklists(session):
        raise ConnectionError("could not connect to postgres")

    monkeypatch.setattr(reviews_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(reviews_module.crud, "list_clause_checklists", fake_list_clause_checklists)

    # Must not raise -- a DB outage shouldn't block reviews from running,
    # it should just mean no clause-specific checklists get applied.
    checklists = await _load_clause_checklists()

    assert checklists == {}


def _build_dotnet_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.sln", "stub")
        zf.writestr(
            "MyApp/MyApp.csproj",
            "<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>",
        )
        zf.writestr("MyApp/Program.cs", "class Program {}")
    return buffer.getvalue()


def _build_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append([1, "Code naming conventions / Code Structure", 1, "=AVERAGE(D2:D2)", "=D1*C1", "=E1/C1", None])
    ws.append([1.1, "Clear and consistent naming conventions", None, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


async def test_run_review_passes_loaded_checklists_through_to_score_category(monkeypatch):
    review_id = "checklist-wiring-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "project.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_dotnet_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    checklists = {(".NET", "2.4"): "Check JWT config"}
    captured_checklists = []

    async def fake_load_clause_checklists():
        return checklists

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_checklists.append(checklists)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_dotnet_build_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "_load_clause_checklists", fake_load_clause_checklists)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_dotnet_build_warnings", fake_check_dotnet_build_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform=".NET",
    )

    assert captured_checklists == [checklists]

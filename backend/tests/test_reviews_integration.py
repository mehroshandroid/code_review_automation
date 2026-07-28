import io
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

import app.api.reviews as reviews_module
from main import app

JACOCO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="INSTRUCTION" missed="10" covered="90"/>
</report>
"""


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "app/build.gradle",
            "apply plugin: 'jacoco'\n"
            "android { compileSdkVersion 34\n defaultConfig { targetSdkVersion 34 } }\n",
        )
        zf.writestr("AndroidManifest.xml", "<manifest />")
        zf.writestr("src/main/java/com/example/MainActivity.java", "class MainActivity {}")
        zf.writestr("build/reports/jacoco/jacocoTestReport.xml", JACOCO_XML)
    return buffer.getvalue()


def _build_xlsx_bytes() -> bytes:
    """Mirrors the real production template's layout (samplefiles/SampleCodeReview.xlsx):
    a title row, a 'Clause' header row, category rows carrying pre-existing rollup
    formulas, and the first sub-row under each category left with a blank id cell.
    Includes categories 1 (6 sub-criteria) and 2 (4 sub-criteria) in full, matching
    CATEGORIES' real counts, since populate_scores consumes rows positionally.
    """
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["<Project Name>", None, None, None, None, None, None])
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append([1, "Code naming conventions / Code Structure", 1, "=AVERAGE(D4:D9)", "=D3*C3", "=E3/C3", None])
    ws.append([None, "Clear and consistent naming conventions", None, None, None, None, None])
    ws.append([1.2, "Clean structure, formatting, and file organization", None, None, None, None, None])
    ws.append([1.3, "No unused, dead, or commented code", None, None, None, None, None])
    ws.append([1.4, "No compile-time warnings", None, None, None, None, None])
    ws.append([1.5, "No unused dependencies", None, None, None, None, None])
    ws.append([1.6, "Latest compile, target sdk and gradle versions", None, None, None, None, None])
    ws.append([2, "Reliability, Security & Observability", 1, "=AVERAGE(D11:D14)", "=D10*C10", "=E10/C10", None])
    ws.append([2.1, "Proper exception handling", None, None, None, None, None])
    ws.append([2.2, "Centralized logging with correct levels", None, None, None, None, None])
    ws.append([2.3, "No sensitive data stored or logged", None, None, None, None, None])
    ws.append([2.4, "Keystore information stored in env or gradle", None, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


def test_full_review_pipeline_in_stub_mode(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    import zipfile as zipfile_module
    with zipfile_module.ZipFile(io.BytesIO(_build_zip_bytes())) as zf:
        zf.extractall(tmp_path)
    from app.analyzer.android_analyzer import gather_code_context
    assert "class MainActivity {}" in gather_code_context(tmp_path)

    real_score_category = reviews_module.score_category
    captured_code_snippets = []

    async def _capturing_score_category(category_name, sub_criteria, descriptions, code_snippets):
        captured_code_snippets.append(code_snippets)
        return await real_score_category(category_name, sub_criteria, descriptions, code_snippets)

    monkeypatch.setattr(reviews_module, "score_category", _capturing_score_category)

    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx",
                    _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
        assert create_response.status_code == 200
        review_id = create_response.json()["review_id"]

        final_state = None
        for _ in range(50):
            progress_response = client.get(f"/api/reviews/{review_id}/progress")
            body = progress_response.json()
            if body["status"] in ("completed", "error"):
                final_state = body
                break
            time.sleep(0.05)

        assert final_state is not None, "review did not finish in time"
        assert final_state["status"] == "completed"
        assert final_state["download_url"] == f"/api/reviews/{review_id}/download"
        assert "total_time_ms" in final_state["stats"]
        assert final_state["test_coverage"] == 90.0
        assert final_state["secrets_found"] == []
        assert final_state["warnings"] == []
        # Stub mode scores every sub-criterion 1 (perfect) across all 5
        # CATEGORIES, so every category's percent_points is 100.0 and the
        # mean across categories is exactly 100.0.
        assert final_state["total_score_pct"] == 100.0
        assert final_state["compile_status"] == "ok"
        assert final_state["lint_issues"] == []

        # Proves the runtime wiring end to end: extraction -> gather_code_context ->
        # _run_review -> score_category actually receives the gathered content, not
        # just that gather_code_context works in isolation on a separate directory.
        assert captured_code_snippets, "score_category was never invoked by _run_review"
        assert any("class MainActivity {}" in snippets for snippets in captured_code_snippets)

        download_response = client.get(final_state["download_url"])
        assert download_response.status_code == 200

        workbook = load_workbook(io.BytesIO(download_response.content))
        ws = workbook.active

        # Category row's rollup formula is untouched -- populate_scores never
        # writes to it, since the real template computes it via formula.
        category_1_row = ws[3]
        assert category_1_row[3].value == "=AVERAGE(D4:D9)"

        # First sub-row under category 1 (blank id cell in the fixture, matched
        # positionally as 1.1) gets its stub score written. Stub mode always
        # scores 1 (perfect), so the remark is correctly left blank -- remarks
        # are reserved for imperfect scores.
        sub_1_1_row = ws[4]
        assert sub_1_1_row[3].value == 1
        assert sub_1_1_row[6].value is None

        # Metadata: project name derived from the uploaded zip's filename
        # (this fixture only has the title placeholder, not the General
        # Remarks/Reviewers/Dated cells -- those are covered end-to-end
        # against the real template in test_excel_handler.py).
        assert ws["A1"].value == "project"

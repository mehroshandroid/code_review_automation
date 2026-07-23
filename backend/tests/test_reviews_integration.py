import io
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

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
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"])
    ws.append(["1", "Code naming conventions / Code Structure", None, None, None, None, None])
    ws.append(["1.1", "Clear and consistent naming", None, None, None, None, None])
    ws.append(["2", "Reliability, Security & Observability", None, None, None, None, None])
    ws.append(["2.1", "Proper exception handling", None, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


def test_full_review_pipeline_in_stub_mode(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    import zipfile as zipfile_module
    with zipfile_module.ZipFile(io.BytesIO(_build_zip_bytes())) as zf:
        zf.extractall(tmp_path)
    from app.analyzer.android_analyzer import gather_code_context
    assert "class MainActivity {}" in gather_code_context(tmp_path)

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

        download_response = client.get(final_state["download_url"])
        assert download_response.status_code == 200

        workbook = load_workbook(io.BytesIO(download_response.content))
        ws = workbook.active
        category_1_row = ws[2]
        assert category_1_row[3].value == 1
        sub_1_1_row = ws[3]
        assert sub_1_1_row[2].value == 1
        assert sub_1_1_row[6].value.startswith("[STUB]")

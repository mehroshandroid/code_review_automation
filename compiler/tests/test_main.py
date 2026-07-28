import io
import zipfile

from fastapi.testclient import TestClient

import main as main_module
from main import app

client = TestClient(app)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("gradlew", "#!/bin/sh\necho fake gradlew")
        zf.writestr("build.gradle", "// stub")
    return buffer.getvalue()


def test_lint_endpoint_returns_ok_with_parsed_issues(monkeypatch):
    async def fake_run_lint(project_dir):
        reports_dir = project_dir / "build" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "lint-results-debug.xml").write_text(
            '<issues format="6"><issue severity="Warning" message="m">'
            '<location file="f.java" line="1"/></issue></issues>'
        )

    monkeypatch.setattr(main_module, "run_lint", fake_run_lint)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
    }


def test_lint_endpoint_returns_build_failed_when_no_report_produced(monkeypatch):
    async def fake_run_lint(project_dir):
        return None  # simulates a build that never got far enough to produce a report

    monkeypatch.setattr(main_module, "run_lint", fake_run_lint)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {"status": "build_failed", "warning_count": None, "issues": []}


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

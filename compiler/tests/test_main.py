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
        return {"returncode": 0, "stdout": "BUILD SUCCESSFUL", "stderr": ""}

    monkeypatch.setattr(main_module, "run_lint", fake_run_lint)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "warning_count": 1,
        "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
    }


def test_lint_endpoint_returns_build_failed_with_the_captured_gradle_output(monkeypatch):
    async def fake_run_lint(project_dir):
        # Simulates a build that never got far enough to produce a report --
        # e.g. a real compile error -- and proves the actual Gradle
        # stdout/stderr is surfaced so a build failure is diagnosable
        # instead of being a silent dead end.
        return {
            "returncode": 1,
            "stdout": "> Task :app:compileDebugJavaWithJavac FAILED",
            "stderr": "error: cannot find symbol",
        }

    monkeypatch.setattr(main_module, "run_lint", fake_run_lint)

    response = client.post("/lint", files={"project": ("project.zip", _build_zip_bytes(), "application/zip")})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "build_failed"
    assert body["warning_count"] is None
    assert body["issues"] == []
    assert "compileDebugJavaWithJavac FAILED" in body["log"]
    assert "cannot find symbol" in body["log"]


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

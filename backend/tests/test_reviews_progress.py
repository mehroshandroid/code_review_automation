from fastapi.testclient import TestClient

from app.api.reviews import _reviews
from main import app

client = TestClient(app)


def test_progress_returns_404_for_unknown_id():
    response = client.get("/api/reviews/does-not-exist/progress")
    assert response.status_code == 404


def test_progress_reflects_stored_state():
    _reviews["fixed-id"] = {
        "status": "processing",
        "phase": "scoring",
        "progress": 60,
        "message": "Scoring category 2",
        "stats": {"ingest_time_ms": 120},
        "download_path": None,
        "error": None,
        "warnings": ["Missing AndroidManifest.xml"],
        "test_coverage": 82.5,
        "secrets_found": [{"file": "Constants.java", "line": 42, "pattern": "api_key"}],
    }
    response = client.get("/api/reviews/fixed-id/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["phase"] == "scoring"
    assert body["progress"] == 60
    assert body["download_url"] is None
    assert body["error"] is None
    assert body["warnings"] == ["Missing AndroidManifest.xml"]
    assert body["test_coverage"] == 82.5
    assert body["secrets_found"] == [{"file": "Constants.java", "line": 42, "pattern": "api_key"}]


def test_progress_defaults_detection_fields_when_absent():
    _reviews["legacy-id"] = {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
    }
    response = client.get("/api/reviews/legacy-id/progress")
    body = response.json()
    assert body["warnings"] == []
    assert body["test_coverage"] is None
    assert body["secrets_found"] == []


def test_progress_includes_download_url_when_completed():
    _reviews["done-id"] = {
        "status": "completed",
        "phase": "completed",
        "progress": 100,
        "message": "Review complete",
        "stats": {"total_time_ms": 500},
        "download_path": "/tmp/whatever/output.xlsx",
        "error": None,
        "warnings": [],
        "test_coverage": None,
        "secrets_found": [],
    }
    response = client.get("/api/reviews/done-id/progress")
    body = response.json()
    assert body["download_url"] == "/api/reviews/done-id/download"

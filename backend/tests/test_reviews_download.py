from pathlib import Path

from fastapi.testclient import TestClient

from app.api.reviews import _reviews
from main import app

client = TestClient(app)


def test_download_returns_404_when_no_result():
    response = client.get("/api/reviews/no-such-review/download")
    assert response.status_code == 404


def test_download_returns_file_and_deletes_it_after(tmp_path: Path):
    output_file = tmp_path / "output.xlsx"
    output_file.write_bytes(b"fake xlsx bytes")
    _reviews["download-ready"] = {
        "status": "completed",
        "phase": "completed",
        "progress": 100,
        "message": "Review complete",
        "stats": {},
        "download_path": str(output_file),
        "error": None,
    }

    response = client.get("/api/reviews/download-ready/download")
    assert response.status_code == 200
    assert response.content == b"fake xlsx bytes"
    assert not output_file.exists()

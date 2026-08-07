import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.settings as settings_module
from app.db.models import Base
from main import app


def _build_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])
    category_specs = [("1", "Code naming conventions / Code Structure", 2), ("2", "Reliability, Security & Observability", 1)]
    for category_id, name, sub_count in category_specs:
        category_row = ws.max_row + 1
        start_row = category_row + 1
        end_row = start_row + sub_count - 1
        ws.append([int(category_id), name, 1, f"=AVERAGE(D{start_row}:D{end_row})", None, None, None])
        for offset in range(1, sub_count + 1):
            ws.append([f"{category_id}.{offset}", f"Sub {category_id}.{offset} description", None, None, None, None, None])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
async def test_sessionmaker(monkeypatch, tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings_module, "new_session", lambda: sessionmaker())
    monkeypatch.setenv("SAMPLE_TEMPLATES_DIR", str(tmp_path))
    yield sessionmaker
    await engine.dispose()


# --- LLM provider ---

def test_get_llm_provider_settings_returns_a_sensible_default_when_unseeded(test_sessionmaker):
    with TestClient(app) as client:
        response = client.get("/api/settings/llm-provider")

    assert response.status_code == 200
    body = response.json()
    assert body["default_llm_provider"] == "ollama"
    assert body["default_ollama_model"] is None


def test_put_llm_provider_settings_updates_and_returns_it(test_sessionmaker):
    with TestClient(app) as client:
        response = client.put("/api/settings/llm-provider", json={"default_llm_provider": "azure", "default_ollama_model": None})
        assert response.status_code == 200
        assert response.json()["default_llm_provider"] == "azure"

        get_response = client.get("/api/settings/llm-provider")
        assert get_response.json()["default_llm_provider"] == "azure"


# --- clause checklists ---

def test_list_clause_checklists_returns_empty_list_initially(test_sessionmaker):
    with TestClient(app) as client:
        response = client.get("/api/settings/clause-checklists")

    assert response.status_code == 200
    assert response.json() == {"checklists": []}


def test_put_clause_checklist_creates_it(test_sessionmaker):
    with TestClient(app) as client:
        response = client.put(
            "/api/settings/clause-checklists/.NET/2.4", json={"checklist_text": "Check JWT config"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == ".NET"
    assert body["sub_id"] == "2.4"
    assert body["checklist_text"] == "Check JWT config"


def test_put_clause_checklist_then_list_shows_it(test_sessionmaker):
    with TestClient(app) as client:
        client.put("/api/settings/clause-checklists/.NET/2.4", json={"checklist_text": "Check JWT config"})
        response = client.get("/api/settings/clause-checklists")

    assert response.json() == {"checklists": [{"platform": ".NET", "sub_id": "2.4", "checklist_text": "Check JWT config"}]}


def test_delete_clause_checklist_removes_it(test_sessionmaker):
    with TestClient(app) as client:
        client.put("/api/settings/clause-checklists/.NET/2.4", json={"checklist_text": "Check JWT config"})
        response = client.delete("/api/settings/clause-checklists/.NET/2.4")
        assert response.status_code == 204

        list_response = client.get("/api/settings/clause-checklists")
        assert list_response.json() == {"checklists": []}


def test_delete_clause_checklist_returns_404_when_not_found(test_sessionmaker):
    with TestClient(app) as client:
        response = client.delete("/api/settings/clause-checklists/.NET/9.9")

    assert response.status_code == 404


# --- sample templates ---

def test_list_sample_templates_returns_empty_list_initially(test_sessionmaker):
    with TestClient(app) as client:
        response = client.get("/api/settings/sample-templates")

    assert response.status_code == 200
    assert response.json() == {"templates": []}


def test_upload_sample_template_stores_it_and_lists_it(test_sessionmaker, tmp_path):
    with TestClient(app) as client:
        response = client.post(
            "/api/settings/sample-templates/Android",
            files={"file": ("android_template.xlsx", b"fake xlsx bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 200
        assert response.json()["filename"] == "android_template.xlsx"

        list_response = client.get("/api/settings/sample-templates")
        templates = list_response.json()["templates"]
        assert len(templates) == 1
        assert templates[0]["platform"] == "Android"
        assert templates[0]["filename"] == "android_template.xlsx"
        # The raw filesystem path is never exposed to the client.
        assert "file_path" not in templates[0]


def test_upload_sample_template_replaces_the_previous_one_for_the_same_platform(test_sessionmaker):
    with TestClient(app) as client:
        client.post(
            "/api/settings/sample-templates/Android",
            files={"file": ("old.xlsx", b"old bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        client.post(
            "/api/settings/sample-templates/Android",
            files={"file": ("new.xlsx", b"new bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        templates = client.get("/api/settings/sample-templates").json()["templates"]

    assert len(templates) == 1
    assert templates[0]["filename"] == "new.xlsx"


def test_delete_sample_template_removes_it(test_sessionmaker):
    with TestClient(app) as client:
        client.post(
            "/api/settings/sample-templates/Android",
            files={"file": ("android_template.xlsx", b"fake xlsx bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        response = client.delete("/api/settings/sample-templates/Android")
        assert response.status_code == 204

        templates = client.get("/api/settings/sample-templates").json()["templates"]
        assert templates == []


def test_delete_sample_template_returns_404_when_not_found(test_sessionmaker):
    with TestClient(app) as client:
        response = client.delete("/api/settings/sample-templates/iOS")

    assert response.status_code == 404


# --- sample template preview ---

def test_preview_sample_template_returns_categories_and_descriptions(test_sessionmaker):
    with TestClient(app) as client:
        client.post(
            "/api/settings/sample-templates/Android",
            files={"file": ("android.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        response = client.get("/api/settings/sample-templates/Android/preview")

    assert response.status_code == 200
    categories = response.json()["categories"]
    assert categories == [
        {
            "id": "1",
            "name": "Code naming conventions / Code Structure",
            "sub_criteria": [
                {"id": "1.1", "description": "Sub 1.1 description"},
                {"id": "1.2", "description": "Sub 1.2 description"},
            ],
        },
        {
            "id": "2",
            "name": "Reliability, Security & Observability",
            "sub_criteria": [{"id": "2.1", "description": "Sub 2.1 description"}],
        },
    ]


def test_preview_sample_template_returns_404_when_no_template_configured(test_sessionmaker):
    with TestClient(app) as client:
        response = client.get("/api/settings/sample-templates/Android/preview")

    assert response.status_code == 404


def test_preview_sample_template_returns_422_when_the_sheet_cannot_be_parsed(test_sessionmaker):
    with TestClient(app) as client:
        client.post(
            "/api/settings/sample-templates/Android",
            files={"file": ("android.xlsx", b"not a real xlsx file", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        response = client.get("/api/settings/sample-templates/Android/preview")

    assert response.status_code == 422

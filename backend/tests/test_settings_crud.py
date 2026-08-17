from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import crud
from app.db.models import Base


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


# --- org_settings ---

async def test_get_org_settings_returns_none_when_not_yet_seeded(session):
    assert await crud.get_org_settings(session) is None


async def test_update_org_settings_creates_the_singleton_row_when_none_exists(session):
    settings = await crud.update_org_settings(session, default_llm_provider="azure", default_ollama_model=None)

    assert settings.default_llm_provider == "azure"
    assert settings.default_ollama_model is None


async def test_update_org_settings_updates_the_existing_row_rather_than_creating_a_second_one(session):
    await crud.update_org_settings(session, default_llm_provider="ollama", default_ollama_model="qwen2.5-coder:7b")
    updated = await crud.update_org_settings(session, default_llm_provider="azure", default_ollama_model=None)

    assert updated.default_llm_provider == "azure"
    assert updated.default_ollama_model is None
    fetched = await crud.get_org_settings(session)
    assert fetched.default_llm_provider == "azure"


# --- clause_checklists ---

async def test_list_clause_checklists_returns_empty_list_when_none_exist(session):
    assert await crud.list_clause_checklists(session) == []


async def test_upsert_clause_checklist_creates_a_new_entry(session):
    checklist = await crud.upsert_clause_checklist(session, platform=".NET", sub_id="2.4", checklist_text="Check JWT config")

    assert checklist.platform == ".NET"
    assert checklist.sub_id == "2.4"
    assert checklist.checklist_text == "Check JWT config"


async def test_upsert_clause_checklist_updates_the_existing_entry_for_the_same_platform_and_sub_id(session):
    await crud.upsert_clause_checklist(session, platform=".NET", sub_id="2.4", checklist_text="Old text")
    await crud.upsert_clause_checklist(session, platform=".NET", sub_id="2.4", checklist_text="New text")

    checklists = await crud.list_clause_checklists(session)
    assert len(checklists) == 1
    assert checklists[0].checklist_text == "New text"


async def test_delete_clause_checklist_removes_it_and_returns_true(session):
    await crud.upsert_clause_checklist(session, platform=".NET", sub_id="2.4", checklist_text="Check JWT config")

    deleted = await crud.delete_clause_checklist(session, platform=".NET", sub_id="2.4")

    assert deleted is True
    assert await crud.list_clause_checklists(session) == []


async def test_delete_clause_checklist_returns_false_when_not_found(session):
    assert await crud.delete_clause_checklist(session, platform=".NET", sub_id="9.9") is False


# --- sample_templates ---

async def test_list_sample_templates_returns_empty_list_when_none_exist(session):
    assert await crud.list_sample_templates(session) == []


async def test_upsert_sample_template_creates_a_new_entry(session):
    template = await crud.upsert_sample_template(
        session, platform="Android", filename="android_template.xlsx",
        file_path="/data/sample-templates/android.xlsx", uploaded_at=datetime.now(timezone.utc),
    )

    assert template.platform == "Android"
    assert template.filename == "android_template.xlsx"


async def test_upsert_sample_template_replaces_the_existing_entry_for_the_same_platform(session):
    await crud.upsert_sample_template(
        session, platform="Android", filename="old.xlsx",
        file_path="/data/sample-templates/old.xlsx", uploaded_at=datetime.now(timezone.utc),
    )
    await crud.upsert_sample_template(
        session, platform="Android", filename="new.xlsx",
        file_path="/data/sample-templates/new.xlsx", uploaded_at=datetime.now(timezone.utc),
    )

    templates = await crud.list_sample_templates(session)
    assert len(templates) == 1
    assert templates[0].filename == "new.xlsx"


async def test_get_sample_template_returns_the_matching_platform(session):
    await crud.upsert_sample_template(
        session, platform="Android", filename="android_template.xlsx",
        file_path="/data/sample-templates/android.xlsx", uploaded_at=datetime.now(timezone.utc),
    )

    template = await crud.get_sample_template(session, "Android")

    assert template is not None
    assert template.filename == "android_template.xlsx"


async def test_get_sample_template_returns_none_when_not_configured(session):
    assert await crud.get_sample_template(session, "iOS") is None


async def test_delete_sample_template_removes_it_and_returns_true(session):
    await crud.upsert_sample_template(
        session, platform="Android", filename="android_template.xlsx",
        file_path="/data/sample-templates/android.xlsx", uploaded_at=datetime.now(timezone.utc),
    )

    deleted = await crud.delete_sample_template(session, "Android")

    assert deleted is True
    assert await crud.get_sample_template(session, "Android") is None


async def test_delete_sample_template_returns_false_when_not_found(session):
    assert await crud.delete_sample_template(session, "iOS") is False

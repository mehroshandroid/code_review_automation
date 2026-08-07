from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import crud
from app.db.models import Base


@pytest.fixture
async def session():
    # In-memory SQLite, dialect-generic JSON type -- keeps this test fast and
    # dependency-free (no live Postgres required), per the design spec.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


async def test_create_project_persists_and_returns_it(session):
    project = await crud.create_project(session, project_id="p1", name="Payments Service")

    assert project.id == "p1"
    assert project.name == "Payments Service"
    assert project.created_at is not None


async def test_create_project_raises_on_duplicate_name(session):
    await crud.create_project(session, project_id="p1", name="Payments Service")

    with pytest.raises(IntegrityError):
        await crud.create_project(session, project_id="p2", name="Payments Service")


async def test_list_projects_returns_newest_first(session):
    await crud.create_project(session, project_id="p1", name="First")
    await crud.create_project(session, project_id="p2", name="Second")

    projects = await crud.list_projects(session)

    assert [p.name for p in projects] == ["Second", "First"]


async def test_list_projects_returns_empty_list_when_none_exist(session):
    assert await crud.list_projects(session) == []


async def test_update_project_name_renames_and_returns_it(session):
    await crud.create_project(session, project_id="p1", name="Old Name")

    project = await crud.update_project_name(session, project_id="p1", name="New Name")

    assert project.id == "p1"
    assert project.name == "New Name"


async def test_update_project_name_returns_none_when_project_does_not_exist(session):
    project = await crud.update_project_name(session, project_id="missing", name="New Name")

    assert project is None


async def test_update_project_name_raises_on_duplicate_name(session):
    await crud.create_project(session, project_id="p1", name="First")
    await crud.create_project(session, project_id="p2", name="Second")

    with pytest.raises(IntegrityError):
        await crud.update_project_name(session, project_id="p2", name="First")


async def test_persist_review_result_creates_a_row_with_the_given_fields(session):
    review = await crud.persist_review_result(
        session,
        review_id="r1",
        project_id=None,
        platform=".NET",
        status="pending_approval",
        project_name="Moove",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_score_pct=82.5,
        llm_provider="azure",
        llm_model=None,
        compile_check_mode="compiler",
        source="upload",
        workbook_path="/data/reviews/r1.xlsx",
        result_data={"warnings": [], "category_scores": []},
    )

    assert review.id == "r1"
    assert review.status == "pending_approval"
    assert review.project_id is None
    assert review.workbook_path == "/data/reviews/r1.xlsx"
    assert review.result_data == {"warnings": [], "category_scores": []}


async def test_persist_review_result_links_to_a_project_when_project_id_given(session):
    await crud.create_project(session, project_id="p1", name="Payments Service")

    review = await crud.persist_review_result(
        session,
        review_id="r1",
        project_id="p1",
        platform="Android",
        status="pending_approval",
        project_name="Payments Service",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        total_score_pct=None,
        llm_provider="ollama",
        llm_model="qwen2.5-coder:7b",
        compile_check_mode="static",
        source="devops",
        workbook_path=None,
        result_data={},
    )

    assert review.project_id == "p1"


async def test_persist_review_result_records_an_error_status(session):
    review = await crud.persist_review_result(
        session,
        review_id="r1",
        project_id=None,
        platform="iOS",
        status="error",
        project_name="MyApp",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        total_score_pct=None,
        llm_provider="azure",
        llm_model=None,
        compile_check_mode="compiler",
        source="upload",
        workbook_path=None,
        result_data={"error": "Ollama request timed out"},
    )

    assert review.status == "error"
    assert review.result_data == {"error": "Ollama request timed out"}


async def _persist(session, review_id, project_id=None, platform="Android", created_at=None, total_score_pct=None):
    return await crud.persist_review_result(
        session,
        review_id=review_id,
        project_id=project_id,
        platform=platform,
        status="pending_approval",
        project_name="MyApp",
        created_at=created_at or datetime.now(timezone.utc),
        completed_at=created_at or datetime.now(timezone.utc),
        total_score_pct=total_score_pct,
        llm_provider="azure",
        llm_model=None,
        compile_check_mode="compiler",
        source="upload",
        workbook_path=None,
        result_data={"category_scores": []},
    )


async def test_get_review_by_id_returns_the_matching_review(session):
    await crud.create_project(session, project_id="p1", name="Payments Service")
    await _persist(session, "r1", project_id="p1", total_score_pct=90)

    review = await crud.get_review_by_id(session, "r1")

    assert review is not None
    assert review.id == "r1"
    assert review.project_id == "p1"
    assert review.total_score_pct == 90


async def test_get_review_by_id_returns_none_when_not_found(session):
    assert await crud.get_review_by_id(session, "does-not-exist") is None


async def test_list_reviews_for_project_returns_only_that_projects_reviews_newest_first(session):
    await crud.create_project(session, project_id="p1", name="Payments Service")
    await crud.create_project(session, project_id="p2", name="Other Project")
    await _persist(session, "r1", project_id="p1", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    await _persist(session, "r2", project_id="p1", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    await _persist(session, "r3", project_id="p2", created_at=datetime(2026, 3, 1, tzinfo=timezone.utc))

    reviews = await crud.list_reviews_for_project(session, "p1")

    assert [r.id for r in reviews] == ["r2", "r1"]


async def test_list_reviews_for_project_returns_empty_list_when_project_has_none(session):
    await crud.create_project(session, project_id="p1", name="Payments Service")

    assert await crud.list_reviews_for_project(session, "p1") == []


async def test_update_review_replaces_category_scores_and_total_score_pct(session):
    await _persist(session, "r1", total_score_pct=50)
    new_scores = [{"id": "1", "name": "Structure", "percent_points": 100, "sub_criteria": []}]

    review = await crud.update_review(session, "r1", category_scores=new_scores, total_score_pct=100)

    assert review.result_data["category_scores"] == new_scores
    assert review.total_score_pct == 100


async def test_update_review_sets_status_and_approved_at_when_moving_to_approved(session):
    await _persist(session, "r1")

    review = await crud.update_review(session, "r1", status="approved")

    assert review.status == "approved"
    assert review.approved_at is not None


async def test_update_review_does_not_set_approved_at_for_other_statuses(session):
    await _persist(session, "r1")

    review = await crud.update_review(session, "r1", status="completed")

    assert review.status == "completed"
    assert review.approved_at is None


async def test_update_review_leaves_category_scores_untouched_when_only_status_given(session):
    await _persist(session, "r1", total_score_pct=77)

    review = await crud.update_review(session, "r1", status="approved")

    assert review.total_score_pct == 77


async def test_update_review_leaves_status_untouched_when_only_category_scores_given(session):
    await _persist(session, "r1")

    review = await crud.update_review(session, "r1", category_scores=[], total_score_pct=None)

    assert review.status == "pending_approval"


async def test_update_review_returns_none_when_review_does_not_exist(session):
    review = await crud.update_review(session, "does-not-exist", status="approved")

    assert review is None

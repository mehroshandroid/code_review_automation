from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.chatbot.tools as tools_module
from app.chatbot.tools import DEFAULT_LIMIT, MAX_LIMIT, _query_reviews
from app.db.models import Base, PlatformReview


@pytest.fixture
async def sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(tools_module, "new_session", lambda: maker())
    yield maker
    await engine.dispose()


async def _add_review(sessionmaker, **overrides):
    defaults = dict(
        id="r1", project_id=None, platform=".NET", status="pending_approval", project_name="Moove",
        created_at=datetime(2025, 6, 1, tzinfo=timezone.utc), completed_at=None,
        total_score_pct=60.0, llm_provider="azure", llm_model=None, compile_check_mode="compiler",
        source="upload", workbook_path=None,
        result_data={
            "category_scores": [
                {"id": "1", "name": "Structure", "percent_points": 50.0, "sub_criteria": [
                    {"id": "1.1", "description": "Naming", "score": 0, "remark": "Inconsistent casing"},
                    {"id": "1.2", "description": "Formatting", "score": 1, "remark": "Fine"},
                ]},
            ],
            "warnings": ["Outdated SDK"],
            "lint_issues": [],
        },
    )
    defaults.update(overrides)
    async with sessionmaker() as session:
        session.add(PlatformReview(**defaults))
        await session.commit()


async def test_query_reviews_filters_by_platform(sessionmaker):
    await _add_review(sessionmaker, id="r1", platform=".NET")
    await _add_review(sessionmaker, id="r2", platform="Android")

    results = await _query_reviews(platform=".NET")

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_platform_match_is_case_insensitive(sessionmaker):
    await _add_review(sessionmaker, id="r1", platform=".NET")

    results = await _query_reviews(platform=".net")

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_year(sessionmaker):
    await _add_review(sessionmaker, id="r1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
    await _add_review(sessionmaker, id="r2", created_at=datetime(2024, 6, 1, tzinfo=timezone.utc))

    results = await _query_reviews(year=2025)

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_date_range(sessionmaker):
    await _add_review(sessionmaker, id="r1", created_at=datetime(2025, 3, 15, tzinfo=timezone.utc))
    await _add_review(sessionmaker, id="r2", created_at=datetime(2025, 9, 1, tzinfo=timezone.utc))

    results = await _query_reviews(start_date="2025-01-01", end_date="2025-06-01")

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_max_score(sessionmaker):
    await _add_review(sessionmaker, id="r1", total_score_pct=60.0)
    await _add_review(sessionmaker, id="r2", total_score_pct=95.0)

    results = await _query_reviews(max_score=70)

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_filters_by_min_score(sessionmaker):
    await _add_review(sessionmaker, id="r1", total_score_pct=60.0)
    await _add_review(sessionmaker, id="r2", total_score_pct=95.0)

    results = await _query_reviews(min_score=90)

    assert [r["id"] for r in results] == ["r2"]


async def test_query_reviews_excludes_errored_reviews(sessionmaker):
    await _add_review(sessionmaker, id="r1", status="pending_approval")
    await _add_review(sessionmaker, id="r2", status="error")

    results = await _query_reviews()

    assert [r["id"] for r in results] == ["r1"]


async def test_query_reviews_returns_only_failing_clauses(sessionmaker):
    await _add_review(sessionmaker, id="r1")

    results = await _query_reviews()

    assert results[0]["failing_clauses"] == [{"id": "1.1", "description": "Naming", "remark": "Inconsistent casing"}]


async def test_query_reviews_includes_full_category_percent_points(sessionmaker):
    await _add_review(sessionmaker, id="r1")

    results = await _query_reviews()

    assert results[0]["category_scores"] == [{"id": "1", "name": "Structure", "percent_points": 50.0}]


async def test_query_reviews_multiple_reviews_show_the_same_categorys_trend(sessionmaker):
    # This is the shape a "why is category X fluctuating across reviews"
    # question needs: the same category name/id with different
    # percent_points across multiple reviews, comparable by the LLM.
    await _add_review(
        sessionmaker, id="r1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        result_data={
            "category_scores": [{"id": "2", "name": "Reliability, Security & Observability", "percent_points": 40.0, "sub_criteria": []}],
            "warnings": [], "lint_issues": [],
        },
    )
    await _add_review(
        sessionmaker, id="r2", created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        result_data={
            "category_scores": [{"id": "2", "name": "Reliability, Security & Observability", "percent_points": 90.0, "sub_criteria": []}],
            "warnings": [], "lint_issues": [],
        },
    )

    results = await _query_reviews()

    percentages = [r["category_scores"][0]["percent_points"] for r in results]
    assert sorted(percentages) == [40.0, 90.0]


async def test_query_reviews_includes_warnings_and_score(sessionmaker):
    await _add_review(sessionmaker, id="r1", total_score_pct=60.0)

    results = await _query_reviews()

    assert results[0]["warnings"] == ["Outdated SDK"]
    assert results[0]["total_score_pct"] == 60.0
    assert results[0]["project_name"] == "Moove"


async def test_query_reviews_respects_limit_and_orders_newest_first(sessionmaker):
    await _add_review(sessionmaker, id="r1", created_at=datetime(2025, 6, 2, tzinfo=timezone.utc))
    await _add_review(sessionmaker, id="r2", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))

    results = await _query_reviews(limit=1)

    assert len(results) == 1
    assert results[0]["id"] == "r1"


def test_default_and_max_limit_constants():
    assert DEFAULT_LIMIT == 20
    assert MAX_LIMIT == 50

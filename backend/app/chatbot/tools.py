from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import extract, select

from app.db.models import PlatformReview
from app.db.session import new_session

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _failing_clauses(result_data: dict) -> list[dict]:
    failing = []
    for category in result_data.get("category_scores", []):
        for sub in category.get("sub_criteria", []):
            if sub.get("score") == 0:
                failing.append({
                    "id": sub.get("id"),
                    "description": sub.get("description"),
                    "remark": sub.get("remark"),
                })
    return failing


def _category_scores(result_data: dict) -> list[dict]:
    return [
        {"id": category.get("id"), "name": category.get("name"), "percent_points": category.get("percent_points")}
        for category in result_data.get("category_scores", [])
    ]


def _review_to_source(review: PlatformReview) -> dict:
    result_data = review.result_data or {}
    return {
        "id": review.id,
        "project_name": review.project_name,
        "platform": review.platform,
        "total_score_pct": float(review.total_score_pct) if review.total_score_pct is not None else None,
        "created_at": review.created_at.isoformat(),
        # Per-category percentages (not just failures) -- this is what lets
        # the agent answer trend/fluctuation questions ("why did Reliability
        # swing between reviews"), by comparing the same category's
        # percent_points across multiple returned reviews.
        "category_scores": _category_scores(result_data),
        "failing_clauses": _failing_clauses(result_data),
        "warnings": result_data.get("warnings", []),
        "lint_issues": result_data.get("lint_issues", []),
    }


async def _query_reviews(
    platform: Optional[str] = None,
    year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_score: Optional[float] = None,
    min_score: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    limit = max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT))
    query = select(PlatformReview).where(PlatformReview.status != "error")
    if platform:
        query = query.where(PlatformReview.platform.ilike(platform))
    if year is not None:
        query = query.where(extract("year", PlatformReview.created_at) == year)
    if start_date:
        query = query.where(PlatformReview.created_at >= datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc))
    if end_date:
        query = query.where(PlatformReview.created_at <= datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc))
    if max_score is not None:
        query = query.where(PlatformReview.total_score_pct <= max_score)
    if min_score is not None:
        query = query.where(PlatformReview.total_score_pct >= min_score)
    query = query.order_by(PlatformReview.created_at.desc()).limit(limit)

    async with new_session() as session:
        result = await session.execute(query)
        reviews = result.scalars().all()
    return [_review_to_source(review) for review in reviews]


@tool
async def query_reviews(
    platform: Optional[str] = None,
    year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_score: Optional[float] = None,
    min_score: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Query code review history.

    platform: e.g. "Android", "iOS", ".NET", "Web (React)". Case-insensitive.
    year: 4-digit year, e.g. 2025.
    start_date/end_date: ISO date strings (YYYY-MM-DD), an alternative to
      year for custom ranges.
    max_score/min_score: bounds on the review's total_score_pct (0-100),
      e.g. max_score=70 for "low-scoring" reviews.
    limit: max reviews to return (default 20, capped at 50).

    Returns, per matching review: id, project_name, platform,
    total_score_pct, created_at, category_scores (every clause/category's
    id/name/percent_points -- compare this same field across the reviews
    returned to spot trends or fluctuations in a specific category over
    time, e.g. "Reliability, Security & Observability" swinging between
    reviews), the clauses it failed (id/description/remark, for root-cause
    detail), and its warnings/lint_issues. Excludes errored reviews (they
    have no scores to reason about).
    """
    return await _query_reviews(platform, year, start_date, end_date, max_score, min_score, limit)

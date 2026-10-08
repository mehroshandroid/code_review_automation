from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.permissions import (
    ALL_ROLES, HOME_PATHS, PERMISSIONS, can, can_view_review, permissions_for, require_permission, visible_project_ids,
)
from app.db import crud
from app.db.models import Base, User

A, M, C, R, P = "admin", "management", "coordinator", "reviewer", "project_manager"

EXPECTED = {
    "dashboard.view_all": {A, M},
    "dashboard.view_assigned": {P},
    "reviews.create": {A, M},
    "reviews.edit": {A, M},
    "reviews.assign_reviewer": {A, M, C},
    "reviews.finalize_own": {A, M, R},
    "reviews.delete": {A},
    "my_reviews.view": {A, M, R},
    "settings.manage": {A, M},
    "users.manage": {A},
    "projects.view": {A, M, C},
    "projects.create": {A, M, C},
    "projects.edit": {A, M, C},
    "cycles.view": {A, M, C},
    "cycles.initiate": {A, M, C},
    "cycles.submit_urls": {A, M, C, P},
    "settings.devops_pat": {A},
    "queue.manage": {A},
    "projects.assign_pm": {A, M, C},
    "projects.delete": {A, M},
    "chat.use": {A, M, P},
}


def _user(role):
    return User(id="u1", email="x@example.com", role=role, is_active=True, password_hash="", created_at=None)


def test_all_roles():
    assert ALL_ROLES == {A, M, C, R, P}


def test_permission_map_matches_spec_exactly():
    assert {key: set(roles) for key, roles in PERMISSIONS.items()} == EXPECTED


@pytest.mark.parametrize("capability", sorted(EXPECTED))
@pytest.mark.parametrize("role", sorted({A, M, C, R, P}))
def test_can_for_every_role_and_capability(role, capability):
    assert can(_user(role), capability) == (role in EXPECTED[capability])


def test_retired_user_role_has_no_capabilities():
    assert permissions_for(_user("user")) == []


def test_home_paths():
    assert HOME_PATHS == {A: "/", M: "/", P: "/", R: "/my-reviews", C: "/"}


def test_permissions_for_is_sorted():
    assert permissions_for(_user(R)) == ["my_reviews.view", "reviews.finalize_own"]


async def test_require_permission_allows_any_of():
    check = require_permission("reviews.create", "settings.manage")
    user = _user(M)
    assert await check(current_user=user) is user


async def test_require_permission_rejects_with_403():
    check = require_permission("users.manage")
    with pytest.raises(HTTPException) as exc:
        await check(current_user=_user(C))
    assert exc.value.status_code == 403


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


def _named(role, user_id):
    return User(id=user_id, email=f"{user_id}@example.com", role=role, is_active=True, password_hash="", created_at=None)


async def test_visible_project_ids_by_role(session):
    await crud.create_project(session, "p1", "One")
    await crud.create_user(session, "pm", "pm@example.com", "h", P)
    await crud.set_managers_for_project(session, "p1", ["pm"])
    assert await visible_project_ids(session, _named(A, "a")) is None
    assert await visible_project_ids(session, _named(M, "m")) is None
    assert await visible_project_ids(session, _named(P, "pm")) == {"p1"}
    assert await visible_project_ids(session, _named(P, "pm-unassigned")) == set()
    assert await visible_project_ids(session, _named(C, "c")) == set()
    assert await visible_project_ids(session, _named(R, "r")) == set()


async def test_can_view_review(session):
    await crud.create_project(session, "p1", "One")
    await crud.create_user(session, "pm", "pm@example.com", "h", P)
    await crud.create_user(session, "rev", "rev@example.com", "h", R)
    await crud.set_managers_for_project(session, "p1", ["pm"])
    linked = await crud.persist_review_result(
        session, review_id="r1", project_id="p1", platform="Android", status="pending_approval",
        project_name="One", created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=1,
        llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="upload",
        workbook_path=None, result_data={},
    )
    unlinked = await crud.persist_review_result(
        session, review_id="r2", project_id=None, platform="Android", status="pending_approval",
        project_name="Adhoc", created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=1,
        llm_provider="azure", llm_model=None, compile_check_mode="compiler", source="upload",
        workbook_path=None, result_data={},
    )
    unlinked = await crud.set_review_reviewer(session, "r2", "rev")
    assert await can_view_review(session, _named(P, "pm"), linked) is True
    assert await can_view_review(session, _named(P, "pm"), unlinked) is False
    assert await can_view_review(session, _named(A, "a"), unlinked) is True
    assert await can_view_review(session, _named(R, "rev"), unlinked) is True
    assert await can_view_review(session, _named(R, "other"), linked) is False
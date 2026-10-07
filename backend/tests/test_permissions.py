import pytest
from fastapi import HTTPException

from app.auth.permissions import ALL_ROLES, HOME_PATHS, PERMISSIONS, can, permissions_for, require_permission
from app.db.models import User

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
    "projects.rename": {A, M, C},
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
    assert HOME_PATHS == {A: "/", M: "/", P: "/", R: "/my-reviews", C: "/projects"}


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

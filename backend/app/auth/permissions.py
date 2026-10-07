"""Single source of truth for who may do what.

Endpoints depend on require_permission(...) instead of listing roles, and
every listing/detail query is scoped through visible_project_ids(...), so
adding a role or widening one only ever means editing PERMISSIONS here.
"""
from fastapi import Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.db.models import User

ADMIN, MANAGEMENT, COORDINATOR, REVIEWER, PROJECT_MANAGER = (
    "admin", "management", "coordinator", "reviewer", "project_manager",
)
ALL_ROLES = frozenset({ADMIN, MANAGEMENT, COORDINATOR, REVIEWER, PROJECT_MANAGER})

_PROJECT_STAFF = frozenset({ADMIN, MANAGEMENT, COORDINATOR})

PERMISSIONS: dict[str, frozenset[str]] = {
    "dashboard.view_all": frozenset({ADMIN, MANAGEMENT}),
    "dashboard.view_assigned": frozenset({PROJECT_MANAGER}),
    "reviews.create": frozenset({ADMIN, MANAGEMENT}),
    "reviews.edit": frozenset({ADMIN, MANAGEMENT}),
    "reviews.assign_reviewer": _PROJECT_STAFF,
    "reviews.finalize_own": frozenset({ADMIN, MANAGEMENT, REVIEWER}),
    "reviews.delete": frozenset({ADMIN}),
    "my_reviews.view": frozenset({ADMIN, MANAGEMENT, REVIEWER}),
    "settings.manage": frozenset({ADMIN, MANAGEMENT}),
    "users.manage": frozenset({ADMIN}),
    "projects.view": _PROJECT_STAFF,
    "projects.create": _PROJECT_STAFF,
    "projects.rename": _PROJECT_STAFF,
    "projects.assign_pm": _PROJECT_STAFF,
    "projects.delete": frozenset({ADMIN, MANAGEMENT}),
    "chat.use": frozenset({ADMIN, MANAGEMENT, PROJECT_MANAGER}),
}

HOME_PATHS: dict[str, str] = {
    ADMIN: "/",
    MANAGEMENT: "/",
    PROJECT_MANAGER: "/",
    REVIEWER: "/my-reviews",
    COORDINATOR: "/projects",
}


def can(user: User, capability: str) -> bool:
    return user.role in PERMISSIONS[capability]


def permissions_for(user: User) -> list[str]:
    return sorted(key for key, roles in PERMISSIONS.items() if user.role in roles)


def require_permission(*capabilities: str):
    """Allow the request if the user holds ANY of the given capabilities."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if not any(can(current_user, capability) for capability in capabilities):
            raise HTTPException(status_code=403, detail="You don't have permission to do this")
        return current_user
    return _check

"""Records workflow emails in notification_outbox; Part 3's mailer sends them."""
from app.db import crud
from app.email import sender as email_sender


async def notify(session, event: str, user_ids, payload: dict) -> list:
    ids = [user_id for user_id in dict.fromkeys(user_ids) if user_id]
    users = await crud.get_users_by_ids(session, ids)
    active = [user_id for user_id in ids if user_id in users and users[user_id].is_active]
    if not active:
        return []
    rows = await crud.add_notifications(session, event, active, payload)
    email_sender.wake()
    return rows


async def project_manager_ids(session, project_id: str) -> list[str]:
    return (await crud.get_manager_ids_for_projects(session, [project_id]))[project_id]


async def admin_ids(session) -> list[str]:
    return await crud.list_active_user_ids_with_roles(session, frozenset({"admin"}))


def cycle_payload(project_name: str, platform: str | None, year: int, quarter: int, **extra) -> dict:
    return {"project_name": project_name, "platform": platform, "year": year, "quarter": quarter, **extra}

"""Admin email section: delivery status, test email, recent emails and retry."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.permissions import require_permission
from app.automation.notify import notify
from app.db import crud
from app.db.session import new_session
from app.email import sender as email_sender
from app.email.config import describe

router = APIRouter(dependencies=[Depends(require_permission("email.manage"))])


def _iso(value):
    return value.isoformat() if value else None


async def _rows(session, rows) -> list[dict]:
    users = await crud.get_users_by_ids(session, [row.recipient_user_id for row in rows])
    result = []
    for row in rows:
        user = users.get(row.recipient_user_id)
        result.append({
            "id": row.id, "event": row.event,
            "recipient_email": user.email if user else None, "recipient_name": user.name if user else None,
            "subject": row.subject, "status": row.status, "attempts": row.attempts, "last_error": row.last_error,
            "created_at": _iso(row.created_at), "sent_at": _iso(row.sent_at),
        })
    return result


@router.get("/api/email/status")
async def email_status():
    return describe()


@router.post("/api/email/test")
async def send_test_email(user=Depends(require_permission("email.manage"))):
    async with new_session() as session:
        rows = await notify(session, "test_email", [user.id], {"link": "/settings"})
        return (await _rows(session, rows))[0]


@router.get("/api/email/outbox")
async def list_outbox(limit: int = Query(50, ge=1, le=200)):
    async with new_session() as session:
        return {"emails": await _rows(session, await crud.list_recent_notifications(session, limit))}


@router.post("/api/email/outbox/{notification_id}/retry")
async def retry_email(notification_id: str):
    async with new_session() as session:
        row = await crud.get_notification(session, notification_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Email not found")
        if row.status != "failed":
            raise HTTPException(status_code=409, detail="Only a failed email can be retried.")
        row = await crud.update_notification(session, row, status="pending", attempts=0, next_attempt_at=None, last_error=None)
        email_sender.wake()
        return (await _rows(session, [row]))[0]

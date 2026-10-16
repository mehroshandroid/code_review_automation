"""Emails every active admin that the server disk is filling up.

Called by deploy/disk-check.sh on the server:
    docker compose exec -T backend python -m app.ops.disk_alert <percent> <free> <mount>
The email goes through the normal outbox, so it is retried and shows in Settings -> Email.
"""
import asyncio
import sys

from app.automation.notify import admin_ids, notify
from app.db.session import new_session


async def alert_admins(percent: int, free: str, mount: str) -> int:
    async with new_session() as session:
        rows = await notify(
            session, "disk_space_low", await admin_ids(session),
            {"percent": percent, "free": free, "mount": mount, "link": "/"},
        )
    return len(rows)


def main(argv: list[str]) -> None:
    percent, free, mount = int(argv[0]), argv[1], argv[2]
    sent = asyncio.run(alert_admins(percent, free, mount))
    print(f"disk alert queued for {sent} admin(s)")


if __name__ == "__main__":
    main(sys.argv[1:])

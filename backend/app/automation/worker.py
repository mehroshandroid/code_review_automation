"""Runs queued cycle reviews one at a time (oldest first), in-process.

Queue and progress live on review_cycle_assignments, so a restart loses
nothing: recover() re-queues runs that were interrupted, plus runs that
failed for system reasons (an admin fix + restart is the retry).
"""
import asyncio
import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import app.api.reviews as reviews_module
from app.automation.config import effective_compile_modes
from app.automation.notify import admin_ids, cycle_payload, notify
from app.db import crud
from app.db.session import new_session
from app.secrets import decrypt

logger = logging.getLogger(__name__)

POLL_SECONDS = 5
PROGRESS_SYNC_SECONDS = 3
NO_PAT = "No usable Azure DevOps PAT is configured in Settings."


def _now():
    return datetime.now(timezone.utc)


async def recover() -> int:
    async with new_session() as session:
        count = await crud.requeue_assignments(session, include_running=True)
    if count:
        logger.info("Review worker: re-queued %d interrupted or system-failed review(s)", count)
    return count


async def _sync_progress(cycle_id: str, platform: str, state: dict) -> None:
    while True:
        await asyncio.sleep(PROGRESS_SYNC_SECONDS)
        async with new_session() as session:
            assignment = await crud.get_assignment(session, cycle_id, platform)
            if assignment is not None:
                await crud.update_assignment(session, assignment, run_phase=state.get("phase"), run_progress=state.get("progress"))


async def _fail(cycle_id: str, platform: str, error: str, kind: str, review_id: str | None) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        await crud.update_assignment(
            session, assignment, run_status="failed", run_error=error, failure_kind=kind,
            review_id=review_id or assignment.review_id, finished_at=_now(),
        )
        payload = cycle_payload(
            project.name, platform, cycle.year, cycle.quarter, error=error, failure_kind=kind,
            review_id=review_id, devops_url=assignment.devops_url,
        )
        await notify(session, "review_failed", await admin_ids(session), payload)
    logger.warning("Review worker: %s %s failed (%s): %s", project.name, platform, kind, error)


async def _succeed(cycle_id: str, platform: str, review_id: str) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        if await crud.set_review_reviewer(session, review_id, assignment.reviewer_id) is None:
            raise RuntimeError("The finished review wasn't saved to the database.")
        await crud.update_assignment(
            session, assignment, run_status="completed", review_id=review_id, run_progress=100,
            run_phase="completed", finished_at=_now(),
        )
        payload = cycle_payload(project.name, platform, cycle.year, cycle.quarter, review_id=review_id, link=f"/reports/{review_id}")
        await notify(session, "review_ready", [assignment.reviewer_id], payload)


async def _process(cycle_id: str, platform: str) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        cycle = await crud.get_cycle_by_id(session, cycle_id)
        project = await crud.get_project(session, cycle.project_id)
        org = await crud.get_org_settings(session)
    pat = decrypt(org.devops_pat_encrypted) if org else None
    if not pat:
        await _fail(cycle_id, platform, NO_PAT, "system", None)
        return
    template_bytes, _ = await reviews_module._resolve_excel_template(None, platform)
    if template_bytes is None:
        await _fail(cycle_id, platform, f"No sample template is configured for {platform} in Settings.", "system", None)
        return

    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(template_bytes)
    state = reviews_module._new_review_state()
    state["project_name"] = project.name
    state["source"] = "devops"
    reviews_module._reviews[review_id] = state

    sync = asyncio.create_task(_sync_progress(cycle_id, platform, state))
    try:
        await reviews_module._run_review(
            review_id, work_dir, work_dir / "android.zip", template_path, True, True, project.name,
            org.default_llm_provider, org.default_ollama_model,
            effective_compile_modes(org.auto_compile_modes)[platform], platform,
            assignment.devops_url, pat, assignment.devops_branch, project_id=project.id,
        )
    finally:
        sync.cancel()

    if state["status"] == "completed":
        await _succeed(cycle_id, platform, review_id)
    else:
        await _fail(cycle_id, platform, state.get("error") or "Review failed", state.get("error_kind") or "system", review_id)


async def run_one() -> bool:
    async with new_session() as session:
        assignment = await crud.claim_next_queued(session)
    if assignment is None:
        return False
    try:
        await _process(assignment.cycle_id, assignment.platform)
    except Exception as exc:
        logger.exception("Review worker: unexpected error on %s/%s", assignment.cycle_id, assignment.platform)
        await _fail(assignment.cycle_id, assignment.platform, f"Unexpected error: {exc}", "system", None)
    return True


async def worker_loop() -> None:
    await recover()
    while True:
        try:
            if not await run_one():
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Review worker loop error")
            await asyncio.sleep(POLL_SECONDS)


def start_worker() -> asyncio.Task:
    return asyncio.create_task(worker_loop())

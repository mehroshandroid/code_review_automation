"""Runs queued cycle reviews one at a time (oldest first), in-process.

Queue and progress live on review_cycle_assignments, so a restart loses
nothing: recover() re-queues runs that were interrupted, plus runs that
failed for system reasons (an admin fix + restart is the retry).
"""
import asyncio
import shutil
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
from app.utils.logger import get_logger

logger = get_logger(__name__)

POLL_SECONDS = 5
PROGRESS_SYNC_SECONDS = 3
NO_PAT = "No usable Azure DevOps PAT is configured in Settings."
STOPPED = "Stopped by an admin."


def _now():
    return datetime.now(timezone.utc)


async def recover() -> int:
    async with new_session() as session:
        count = await crud.requeue_assignments(session, include_running=True)
    if count:
        logger.info("Review worker: re-queued %d interrupted or system-failed review(s)", count)
    return count


async def _sync_progress(cycle_id: str, platform: str, state: dict, run_task: asyncio.Task) -> None:
    """Copies progress to the row, and cancels the run when an admin pauses the queue or stops it."""
    while True:
        await asyncio.sleep(PROGRESS_SYNC_SECONDS)
        async with new_session() as session:
            assignment = await crud.get_assignment(session, cycle_id, platform)
            if assignment is None:
                continue
            if assignment.cancel_requested:
                state["cancelled"] = assignment.cancel_requested
                run_task.cancel()
                return
            await crud.update_assignment(session, assignment, run_phase=state.get("phase"), run_progress=state.get("progress"))


async def _cancelled(cycle_id: str, platform: str, reason: str) -> None:
    async with new_session() as session:
        assignment = await crud.get_assignment(session, cycle_id, platform)
        if reason == "pause":
            await crud.update_assignment(
                session, assignment, run_status="queued", queued_at=await crud.front_of_queue_time(session),
                cancel_requested=None, run_phase=None, run_progress=None, started_at=None,
            )
        else:
            await crud.update_assignment(
                session, assignment, run_status="failed", failure_kind="stopped", run_error=STOPPED,
                finished_at=_now(), cancel_requested=None,
            )
    logger.info("Review worker: %s/%s %s by an admin", cycle_id, platform, "paused" if reason == "pause" else "stopped")


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
        superseded = assignment.review_id
        if superseded and superseded != review_id:
            # A re-run replaced an earlier, unapproved review: take it off the reviewer's list.
            if (await crud.get_review_statuses(session, [superseded])).get(superseded) != "approved":
                await crud.set_review_reviewer(session, superseded, None)
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

    # Per-run overrides from the admin queue page win over the org defaults.
    provider = assignment.override_llm_provider or org.default_llm_provider
    model = assignment.override_llm_model if assignment.override_llm_provider else org.default_ollama_model
    compile_mode = assignment.override_compile_mode or effective_compile_modes(org.auto_compile_modes)[platform]

    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    state = reviews_module._new_review_state()
    state["project_name"] = project.name
    state["source"] = "devops"
    reviews_module._reviews[review_id] = state
    sync = None
    try:
        template_path = work_dir / "template.xlsx"
        template_path.write_bytes(template_bytes)
        run_task = asyncio.create_task(reviews_module._run_review(
            review_id, work_dir, work_dir / "android.zip", template_path, True, True, project.name,
            provider, model, compile_mode, platform,
            assignment.devops_url, pat, assignment.devops_branch, project_id=project.id,
        ))
        sync = asyncio.create_task(_sync_progress(cycle_id, platform, state, run_task))
        try:
            await run_task
        except asyncio.CancelledError:
            if not state.get("cancelled"):
                raise  # the worker itself is shutting down
    finally:
        if sync is not None:
            sync.cancel()
        # Nobody downloads automated runs from the live path (the workbook is
        # already persisted), so drop the in-memory state and temp files now.
        reviews_module._reviews.pop(review_id, None)
        shutil.rmtree(work_dir, ignore_errors=True)

    if state.get("cancelled"):
        await _cancelled(cycle_id, platform, state["cancelled"])
        return
    if state["status"] == "completed":
        await _succeed(cycle_id, platform, review_id)
    else:
        await _fail(cycle_id, platform, state.get("error") or "Review failed", state.get("error_kind") or "system", review_id)


async def run_one() -> bool:
    async with new_session() as session:
        if (await crud.get_queue_state(session)).paused:
            return False
        assignment = await crud.claim_next_queued(session)
    if assignment is None:
        return False
    try:
        await _process(assignment.cycle_id, assignment.platform)
    except Exception as exc:
        logger.exception("Review worker: unexpected error on %s/%s", assignment.cycle_id, assignment.platform)
        error = f"Unexpected error: {exc}"
        try:
            await _fail(assignment.cycle_id, assignment.platform, error, "system", None)
        except Exception:
            logger.exception("Review worker: couldn't record the failure normally; marking the row failed directly")
            await _mark_failed(assignment.cycle_id, assignment.platform, error)
    return True


async def _mark_failed(cycle_id: str, platform: str, error: str) -> None:
    """Last resort so a row is never left 'running' (no notification)."""
    try:
        async with new_session() as session:
            assignment = await crud.get_assignment(session, cycle_id, platform)
            if assignment is not None:
                await crud.update_assignment(
                    session, assignment, run_status="failed", failure_kind="system", run_error=error, finished_at=_now(),
                )
    except Exception:
        logger.exception("Review worker: couldn't mark %s/%s failed; it will be re-queued on restart", cycle_id, platform)


async def worker_loop() -> None:
    logger.info("Review worker started")
    while True:
        try:
            await recover()
            break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Review worker: startup recovery failed; retrying")
            await asyncio.sleep(POLL_SECONDS)
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

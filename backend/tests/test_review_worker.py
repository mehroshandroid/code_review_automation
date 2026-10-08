import asyncio
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.reviews as reviews_module
import app.automation.worker as worker
from app.db import crud
from app.db.models import Base
from app.secrets import encrypt

URL = "https://dev.azure.com/org/Proj/_git/repo"


@pytest.fixture
async def db(monkeypatch):
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "new_session", lambda: maker())
    monkeypatch.setattr(worker, "PROGRESS_SYNC_SECONDS", 0.01)

    async def fake_template(file, platform):
        return b"xlsx", "template.xlsx"

    monkeypatch.setattr(reviews_module, "_resolve_excel_template", fake_template)
    async with maker() as s:
        await crud.create_user(s, "rev", "rev@example.com", "h", "reviewer")
        await crud.create_user(s, "adm", "adm@example.com", "h", "admin")
        await crud.create_project(s, "p1", "Alpha")
        await crud.create_cycle(s, "c1", "p1", 2026, 4, None, [("Android", "rev"), ("iOS", "rev")])
        await crud.update_devops_pat(s, encrypt("the-pat"), "-pat", "adm")
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, run_status="queued", queued_at=datetime.now(timezone.utc), devops_url=URL, devops_branch="main")
    yield maker
    await engine.dispose()


def _fake_pipeline(maker, outcome, error=None, error_kind=None, captured=None):
    async def fake_run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
                              llm_provider="azure", ollama_model=None, compile_check_mode="compiler", platform="Android",
                              devops_repo_url=None, devops_pat=None, devops_branch=None, project_id=None, clause_overrides=None):
        if captured is not None:
            captured.update(locals())
        state = reviews_module._reviews[review_id]
        state["phase"], state["progress"] = "scoring", 60
        import asyncio
        await asyncio.sleep(0.05)
        state["status"] = outcome
        state["error"], state["error_kind"] = error, error_kind
        async with maker() as s:
            await crud.persist_review_result(
                s, review_id=review_id, project_id=project_id, platform=platform,
                status="pending_approval" if outcome == "completed" else "error", project_name=project_name,
                created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=70, llm_provider=llm_provider,
                llm_model=ollama_model, compile_check_mode=compile_check_mode, source="devops", workbook_path=None, result_data={},
            )
    return fake_run_review


async def test_success_links_review_sets_reviewer_and_notifies(db, monkeypatch):
    captured = {}
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed", captured=captured))
    assert await worker.run_one() is True
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        review = await crud.get_review_by_id(s, a.review_id)
        ready = await crud.list_notifications(s, "review_ready")
    assert a.run_status == "completed" and a.run_progress == 100 and a.finished_at is not None and a.attempts == 1
    assert review.reviewer_id == "rev" and review.project_name == "Alpha"
    assert [n.recipient_user_id for n in ready] == ["rev"] and ready[0].payload["link"] == f"/reports/{a.review_id}"
    assert captured["devops_pat"] == "the-pat" and captured["devops_repo_url"] == URL and captured["devops_branch"] == "main"
    assert captured["compile_check_mode"] == "compiler" and captured["platform"] == "Android" and captured["project_id"] == "p1"
    assert await worker.run_one() is False


async def test_url_failure_records_error_and_notifies_admins(db, monkeypatch):
    async with db() as s:
        await crud.create_user(s, "adm-off", "off@example.com", "h", "admin")
        await crud.update_user(s, "adm-off", is_active=False)
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "error", "Repository or branch not found.", "url"))
    await worker.run_one()
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        failed = await crud.list_notifications(s, "review_failed")
        review = await crud.get_review_by_id(s, a.review_id)
    assert (a.run_status, a.failure_kind, a.run_error) == ("failed", "url", "Repository or branch not found.")
    assert review.status == "error"
    assert [n.recipient_user_id for n in failed] == ["adm"]
    assert failed[0].payload["error"] == "Repository or branch not found." and failed[0].payload["failure_kind"] == "url"


async def test_unclassified_failure_is_system(db, monkeypatch):
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "error", "LLM unreachable"))
    await worker.run_one()
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).failure_kind == "system"


async def test_missing_pat_is_a_system_failure(db, monkeypatch):
    async with db() as s:
        settings = await crud.get_org_settings(s)
        settings.devops_pat_encrypted = None
        await s.commit()

    async def must_not_run(*args, **kwargs):
        raise AssertionError("pipeline must not run without a PAT")

    monkeypatch.setattr(reviews_module, "_run_review", must_not_run)
    await worker.run_one()
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        failed = await crud.list_notifications(s, "review_failed")
    assert (a.run_status, a.failure_kind, a.run_error) == ("failed", "system", "No usable Azure DevOps PAT is configured in Settings.")
    assert len(failed) == 1


async def test_progress_is_synced_while_running(db, monkeypatch):
    seen = []
    real_update = crud.update_assignment

    async def spy(session, assignment, **fields):
        if "run_phase" in fields and fields.get("run_phase") == "scoring":
            seen.append(fields.get("run_progress"))
        return await real_update(session, assignment, **fields)

    monkeypatch.setattr(worker.crud, "update_assignment", spy)
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed"))
    await worker.run_one()
    assert 60 in seen


async def test_recover_requeues_running_and_system_failures_only(db):
    async with db() as s:
        android = await crud.get_assignment(s, "c1", "Android")
        ios = await crud.get_assignment(s, "c1", "iOS")
        await crud.update_assignment(s, android, run_status="running")
        await crud.update_assignment(s, ios, run_status="failed", failure_kind="url")
    assert await worker.recover() == 1
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"
        assert (await crud.get_assignment(s, "c1", "iOS")).run_status == "failed"


async def test_successful_rerun_unassigns_the_superseded_review(db, monkeypatch):
    async with db() as s:
        await crud.persist_review_result(
            s, review_id="old", project_id="p1", platform="Android", status="pending_approval", project_name="Alpha",
            created_at=datetime.now(timezone.utc), completed_at=None, total_score_pct=50, llm_provider="azure",
            llm_model=None, compile_check_mode="compiler", source="devops", workbook_path=None, result_data={},
        )
        await crud.set_review_reviewer(s, "old", "rev")
        a = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, a, review_id="old")
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed"))
    await worker.run_one()
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        old = await crud.get_review_by_id(s, "old")
    assert a.review_id != "old" and old.reviewer_id is None


async def test_run_cleans_up_memory_and_temp_dir(db, monkeypatch):
    seen = {}
    fake = _fake_pipeline(db, "completed", captured=seen)

    async def pipeline_writing_output(review_id, work_dir, *args, **kwargs):
        (work_dir / "output.xlsx").write_bytes(b"x")
        await fake(review_id, work_dir, *args, **kwargs)

    monkeypatch.setattr(reviews_module, "_run_review", pipeline_writing_output)
    await worker.run_one()
    assert seen["review_id"] not in reviews_module._reviews
    assert not seen["work_dir"].exists()


async def test_crash_with_failing_fallback_still_leaves_the_row_failed(db, monkeypatch):
    async def boom_process(cycle_id, platform):
        raise RuntimeError("pipeline exploded")

    real_fail = worker._fail
    calls = {"n": 0}

    async def flaky_fail(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("db blip")

    monkeypatch.setattr(worker, "_process", boom_process)
    monkeypatch.setattr(worker, "_fail", flaky_fail)
    assert await worker.run_one() is True
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
    assert a.run_status == "failed" and a.failure_kind == "system" and "pipeline exploded" in a.run_error
    assert calls["n"] == 1 and real_fail is not None


async def test_recover_is_retried_until_the_database_answers(db, monkeypatch):
    attempts = {"n": 0}
    real_recover = worker.recover

    async def flaky_recover():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("db not ready")
        return await real_recover()

    async def stop_after_recovery():
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "recover", flaky_recover)
    monkeypatch.setattr(worker, "run_one", stop_after_recovery)
    monkeypatch.setattr(worker, "POLL_SECONDS", 0)
    with pytest.raises(asyncio.CancelledError):
        await worker.worker_loop()
    assert attempts["n"] == 2


def _slow_pipeline(started: asyncio.Event, persisted: list):
    async def fake_run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name, *args, **kwargs):
        state = reviews_module._reviews[review_id]
        state["phase"], state["progress"] = "scoring", 30
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            if not state.get("cancelled"):
                persisted.append(review_id)
    return fake_run_review


async def _wait_until_started(started):
    await asyncio.wait_for(started.wait(), 2)


async def test_paused_queue_claims_nothing(db):
    async with db() as s:
        await crud.set_queue_paused(s, True, "adm")
    assert await worker.run_one() is False
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "queued"


async def test_pause_cancels_the_running_review_and_requeues_it_first(db, monkeypatch):
    started, persisted = asyncio.Event(), []
    monkeypatch.setattr(reviews_module, "_run_review", _slow_pipeline(started, persisted))
    task = asyncio.create_task(worker.run_one())
    await _wait_until_started(started)
    async with db() as s:
        ios = await crud.get_assignment(s, "c1", "iOS")
        await crud.update_assignment(s, ios, run_status="queued", queued_at=datetime(2020, 1, 1, tzinfo=timezone.utc), devops_url=URL)
        android = await crud.get_assignment(s, "c1", "Android")
        await crud.update_assignment(s, android, cancel_requested="pause")
    assert await asyncio.wait_for(task, 2) is True
    async with db() as s:
        android = await crud.get_assignment(s, "c1", "Android")
        keys = await crud.list_queued_keys(s)
    assert android.run_status == "queued" and android.cancel_requested is None and android.run_progress is None
    assert keys == [("c1", "Android"), ("c1", "iOS")]
    assert persisted == []


async def test_stop_fails_the_run_without_storing_a_review(db, monkeypatch):
    started, persisted = asyncio.Event(), []
    monkeypatch.setattr(reviews_module, "_run_review", _slow_pipeline(started, persisted))
    task = asyncio.create_task(worker.run_one())
    await _wait_until_started(started)
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), cancel_requested="stop")
    await asyncio.wait_for(task, 2)
    async with db() as s:
        a = await crud.get_assignment(s, "c1", "Android")
        failed = await crud.list_notifications(s, "review_failed")
    assert (a.run_status, a.failure_kind, a.run_error, a.cancel_requested) == ("failed", "stopped", "Stopped by an admin.", None)
    assert a.finished_at is not None and persisted == [] and failed == []


async def test_stopped_runs_are_not_requeued(db):
    async with db() as s:
        await crud.update_assignment(s, await crud.get_assignment(s, "c1", "Android"), run_status="failed", failure_kind="stopped")
    assert await worker.recover() == 0


async def test_worker_cancellation_is_not_mistaken_for_a_pause(db, monkeypatch):
    started, persisted = asyncio.Event(), []
    monkeypatch.setattr(reviews_module, "_run_review", _slow_pipeline(started, persisted))
    task = asyncio.create_task(worker.run_one())
    await _wait_until_started(started)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with db() as s:
        assert (await crud.get_assignment(s, "c1", "Android")).run_status == "running"


async def test_overrides_reach_the_pipeline(db, monkeypatch):
    captured = {}
    async with db() as s:
        await crud.update_assignment(
            s, await crud.get_assignment(s, "c1", "Android"),
            override_llm_provider="claude", override_compile_mode="static",
        )
    monkeypatch.setattr(reviews_module, "_run_review", _fake_pipeline(db, "completed", captured=captured))
    await worker.run_one()
    assert captured["llm_provider"] == "claude" and captured["ollama_model"] is None
    assert captured["compile_check_mode"] == "static"


async def test_cancelled_pipeline_does_not_persist(monkeypatch, tmp_path):
    calls = []

    async def record(*args, **kwargs):
        calls.append(args)

    async def slow_fetch(repo_url, pat, branch=None):
        await asyncio.sleep(10)

    monkeypatch.setattr(reviews_module, "_persist_review_result", record)
    monkeypatch.setattr(reviews_module, "fetch_repo_zip", slow_fetch)
    reviews_module._reviews["cx"] = state = reviews_module._new_review_state()
    task = asyncio.create_task(reviews_module._run_review(
        "cx", tmp_path, tmp_path / "a.zip", tmp_path / "t.xlsx", True, True, "P",
        devops_repo_url=URL, devops_pat="pat",
    ))
    await asyncio.sleep(0.05)
    state["cancelled"] = "pause"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == []

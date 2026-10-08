import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, delete, extract, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClauseChecklist, NotificationOutbox, OrgSettings, PlatformReview, Project, ProjectManager, ProjectPlatform,
    ReviewCycle, ReviewCycleAssignment, ReviewQueueState, SampleTemplate, User,
)
from app.quarterly import sort_platforms


async def create_project(session: AsyncSession, project_id: str, name: str) -> Project:
    project = Project(id=project_id, name=name, created_at=datetime.now(timezone.utc))
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project




async def update_project_name(session: AsyncSession, project_id: str, name: str) -> Optional[Project]:
    project = await session.get(Project, project_id)
    if project is None:
        return None
    project.name = name
    await session.commit()
    await session.refresh(project)
    return project


async def persist_review_result(
    session: AsyncSession,
    review_id: str,
    project_id: Optional[str],
    platform: str,
    status: str,
    project_name: str,
    created_at: datetime,
    completed_at: Optional[datetime],
    total_score_pct: Optional[float],
    llm_provider: str,
    llm_model: Optional[str],
    compile_check_mode: str,
    source: str,
    workbook_path: Optional[str],
    result_data: dict,
    created_by: Optional[str] = None,
    approved_by: Optional[str] = None,
    approved_at: Optional[datetime] = None,
) -> PlatformReview:
    review = PlatformReview(
        id=review_id,
        project_id=project_id,
        platform=platform,
        status=status,
        project_name=project_name,
        created_at=created_at,
        completed_at=completed_at,
        total_score_pct=total_score_pct,
        llm_provider=llm_provider,
        llm_model=llm_model,
        compile_check_mode=compile_check_mode,
        source=source,
        workbook_path=workbook_path,
        result_data=result_data,
        created_by=created_by,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review


async def get_review_by_id(session: AsyncSession, review_id: str) -> Optional[PlatformReview]:
    return await session.get(PlatformReview, review_id)


async def get_project(session: AsyncSession, project_id: str) -> Optional[Project]:
    return await session.get(Project, project_id)


async def list_reviews_for_project(session: AsyncSession, project_id: str) -> list[PlatformReview]:
    result = await session.execute(
        select(PlatformReview)
        .where(PlatformReview.project_id == project_id)
        .order_by(PlatformReview.created_at.desc())
    )
    return list(result.scalars().all())




async def get_latest_review_for_platform(session: AsyncSession, platform: str) -> Optional[PlatformReview]:
    query = (
        select(PlatformReview)
        .where(PlatformReview.platform.ilike(platform))
        .order_by(PlatformReview.created_at.desc())
        .limit(1)
    )
    result = await session.execute(query)
    return result.scalars().first()




async def update_review(
    session: AsyncSession,
    review_id: str,
    category_scores: Optional[list] = None,
    total_score_pct: Optional[float] = None,
    status: Optional[str] = None,
) -> Optional[PlatformReview]:
    review = await session.get(PlatformReview, review_id)
    if review is None:
        return None
    if category_scores is not None:
        review.result_data = {**review.result_data, "category_scores": category_scores}
        review.total_score_pct = total_score_pct
    if status is not None:
        review.status = status
        if status == "approved" and review.approved_at is None:
            review.approved_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(review)
    return review




async def set_review_reviewer(session: AsyncSession, review_id: str, reviewer_id: Optional[str]) -> Optional[PlatformReview]:
    review = await session.get(PlatformReview, review_id)
    if review is None:
        return None
    review.reviewer_id = reviewer_id
    await session.commit()
    await session.refresh(review)
    return review


async def delete_review(session: AsyncSession, review_id: str) -> bool:
    result = await session.execute(delete(PlatformReview).where(PlatformReview.id == review_id))
    await session.commit()
    return result.rowcount > 0


# --- org_settings (singleton, id=1) ---

_ORG_SETTINGS_ID = 1


async def get_org_settings(session: AsyncSession) -> Optional[OrgSettings]:
    return await session.get(OrgSettings, _ORG_SETTINGS_ID)


async def update_org_settings(
    session: AsyncSession, default_llm_provider: str, default_ollama_model: Optional[str]
) -> OrgSettings:
    settings = await session.get(OrgSettings, _ORG_SETTINGS_ID)
    if settings is None:
        settings = OrgSettings(id=_ORG_SETTINGS_ID)
        session.add(settings)
    settings.default_llm_provider = default_llm_provider
    settings.default_ollama_model = default_ollama_model
    settings.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(settings)
    return settings


# --- clause_checklists ---

async def list_clause_checklists(session: AsyncSession) -> list[ClauseChecklist]:
    result = await session.execute(select(ClauseChecklist).order_by(ClauseChecklist.platform, ClauseChecklist.sub_id))
    return list(result.scalars().all())


async def upsert_clause_checklist(session: AsyncSession, platform: str, sub_id: str, checklist_text: str) -> ClauseChecklist:
    result = await session.execute(
        select(ClauseChecklist).where(ClauseChecklist.platform == platform, ClauseChecklist.sub_id == sub_id)
    )
    checklist = result.scalar_one_or_none()
    if checklist is None:
        checklist = ClauseChecklist(id=str(uuid.uuid4()), platform=platform, sub_id=sub_id, checklist_text=checklist_text)
        session.add(checklist)
    else:
        checklist.checklist_text = checklist_text
    await session.commit()
    await session.refresh(checklist)
    return checklist


async def delete_clause_checklist(session: AsyncSession, platform: str, sub_id: str) -> bool:
    result = await session.execute(
        delete(ClauseChecklist).where(ClauseChecklist.platform == platform, ClauseChecklist.sub_id == sub_id)
    )
    await session.commit()
    return result.rowcount > 0


# --- sample_templates ---

async def list_sample_templates(session: AsyncSession) -> list[SampleTemplate]:
    result = await session.execute(select(SampleTemplate).order_by(SampleTemplate.platform))
    return list(result.scalars().all())


async def get_sample_template(session: AsyncSession, platform: str) -> Optional[SampleTemplate]:
    return await session.get(SampleTemplate, platform)


async def upsert_sample_template(
    session: AsyncSession, platform: str, filename: str, file_path: str, uploaded_at: datetime
) -> SampleTemplate:
    template = await session.get(SampleTemplate, platform)
    if template is None:
        template = SampleTemplate(platform=platform)
        session.add(template)
    template.filename = filename
    template.file_path = file_path
    template.uploaded_at = uploaded_at
    await session.commit()
    await session.refresh(template)
    return template


async def delete_sample_template(session: AsyncSession, platform: str) -> bool:
    result = await session.execute(delete(SampleTemplate).where(SampleTemplate.platform == platform))
    await session.commit()
    return result.rowcount > 0




async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    return await session.get(User, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())




async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def list_projects(session: AsyncSession, project_ids: Optional[set[str]] = None) -> list[Project]:
    if project_ids is not None and not project_ids:
        return []
    query = select(Project).order_by(Project.created_at.desc())
    if project_ids is not None:
        query = query.where(Project.id.in_(project_ids))
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_reviews(
    session: AsyncSession,
    year: int,
    platform: Optional[str] = None,
    project_id: Optional[str] = None,
    project_ids: Optional[set[str]] = None,
) -> list[PlatformReview]:
    if project_ids is not None and not project_ids:
        return []
    query = select(PlatformReview).where(extract("year", PlatformReview.created_at) == year)
    if platform:
        query = query.where(PlatformReview.platform.ilike(platform))
    if project_id:
        query = query.where(PlatformReview.project_id == project_id)
    if project_ids is not None:
        query = query.where(PlatformReview.project_id.in_(project_ids))
    query = query.order_by(PlatformReview.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_review_years(session: AsyncSession, project_ids: Optional[set[str]] = None) -> list[int]:
    if project_ids is not None and not project_ids:
        return []
    query = select(extract("year", PlatformReview.created_at)).distinct()
    if project_ids is not None:
        query = query.where(PlatformReview.project_id.in_(project_ids))
    result = await session.execute(query)
    return sorted({int(year) for (year,) in result.all()})


async def list_reviews_for_reviewer(session: AsyncSession, user_id: str) -> list[PlatformReview]:
    result = await session.execute(
        select(PlatformReview)
        .where(PlatformReview.reviewer_id == user_id)
        .order_by(PlatformReview.created_at.desc())
    )
    return list(result.scalars().all())


async def list_reviewer_candidates(session: AsyncSession, roles: frozenset[str]) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.role.in_(roles), User.is_active.is_(True))
        .order_by(User.email)
    )
    return list(result.scalars().all())


# --- project managers ---

async def get_project_ids_for_manager(session: AsyncSession, user_id: str) -> set[str]:
    result = await session.execute(select(ProjectManager.project_id).where(ProjectManager.user_id == user_id))
    return {project_id for (project_id,) in result.all()}


async def get_project_ids_for_managers(session: AsyncSession, user_ids: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return mapping
    result = await session.execute(
        select(ProjectManager.user_id, ProjectManager.project_id)
        .where(ProjectManager.user_id.in_(user_ids))
        .order_by(ProjectManager.project_id)
    )
    for user_id, project_id in result.all():
        mapping[user_id].append(project_id)
    return mapping


async def get_manager_ids_for_projects(session: AsyncSession, project_ids: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {project_id: [] for project_id in project_ids}
    if not project_ids:
        return mapping
    result = await session.execute(
        select(ProjectManager.project_id, ProjectManager.user_id)
        .where(ProjectManager.project_id.in_(project_ids))
        .order_by(ProjectManager.user_id)
    )
    for project_id, user_id in result.all():
        mapping[project_id].append(user_id)
    return mapping


async def set_managers_for_project(session: AsyncSession, project_id: str, user_ids: list[str]) -> None:
    await session.execute(delete(ProjectManager).where(ProjectManager.project_id == project_id))
    for user_id in dict.fromkeys(user_ids):
        session.add(ProjectManager(user_id=user_id, project_id=project_id))
    await session.commit()


async def clear_projects_for_manager(session: AsyncSession, user_id: str) -> None:
    await session.execute(delete(ProjectManager).where(ProjectManager.user_id == user_id))
    await session.commit()


async def count_reviews_by_project(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(PlatformReview.project_id, func.count())
        .where(PlatformReview.project_id.is_not(None))
        .group_by(PlatformReview.project_id)
    )
    return {project_id: count for project_id, count in result.all()}


async def count_reviews_for_project(session: AsyncSession, project_id: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(PlatformReview).where(PlatformReview.project_id == project_id)
    )
    return result.scalar_one()


async def delete_project(session: AsyncSession, project_id: str) -> bool:
    # Explicit, not just ON DELETE CASCADE: SQLite (tests) doesn't enforce FKs by default.
    cycle_ids = select(ReviewCycle.id).where(ReviewCycle.project_id == project_id)
    await session.execute(delete(ReviewCycleAssignment).where(ReviewCycleAssignment.cycle_id.in_(cycle_ids)))
    await session.execute(delete(ReviewCycle).where(ReviewCycle.project_id == project_id))
    await session.execute(delete(ProjectPlatform).where(ProjectPlatform.project_id == project_id))
    await session.execute(delete(ProjectManager).where(ProjectManager.project_id == project_id))
    result = await session.execute(delete(Project).where(Project.id == project_id))
    await session.commit()
    return result.rowcount > 0


async def create_user(
    session: AsyncSession, user_id: str, email: str, password_hash: str, role: str, name: Optional[str] = None,
) -> User:
    user = User(
        id=user_id, email=email, password_hash=password_hash, role=role, name=(name or "").strip() or None,
        is_active=True, created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession, user_id: str,
    role: Optional[str] = None, is_active: Optional[bool] = None, password_hash: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[User]:
    user = await session.get(User, user_id)
    if user is None:
        return None
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if password_hash is not None:
        user.password_hash = password_hash
    if name is not None:
        user.name = name.strip() or None
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: str) -> bool:
    await session.execute(delete(ProjectManager).where(ProjectManager.user_id == user_id))
    result = await session.execute(delete(User).where(User.id == user_id))
    await session.commit()
    return result.rowcount > 0


# --- quarterly ---

async def get_platforms_for_projects(session: AsyncSession, project_ids: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {project_id: [] for project_id in project_ids}
    if not project_ids:
        return mapping
    result = await session.execute(
        select(ProjectPlatform.project_id, ProjectPlatform.platform).where(ProjectPlatform.project_id.in_(project_ids))
    )
    for project_id, platform in result.all():
        mapping[project_id].append(platform)
    return {project_id: sort_platforms(platforms) for project_id, platforms in mapping.items()}


async def set_platforms_for_project(session: AsyncSession, project_id: str, platforms: list[str]) -> None:
    await session.execute(delete(ProjectPlatform).where(ProjectPlatform.project_id == project_id))
    for platform in sort_platforms(platforms):
        session.add(ProjectPlatform(project_id=project_id, platform=platform))
    await session.commit()


async def list_review_coverage_rows(session: AsyncSession, project_ids: list[str], year: int) -> list:
    """Just the columns quarterly coverage needs (no result_data JSON), newest first, excluding errors."""
    if not project_ids:
        return []
    result = await session.execute(
        select(PlatformReview.id, PlatformReview.project_id, PlatformReview.platform, PlatformReview.created_at)
        .where(
            PlatformReview.project_id.in_(project_ids),
            PlatformReview.status != "error",
            extract("year", PlatformReview.created_at) == year,
        )
        .order_by(PlatformReview.created_at.desc())
    )
    return list(result.all())


async def list_cycles_for_projects_in_year(session: AsyncSession, project_ids: list[str], year: int) -> list[ReviewCycle]:
    if not project_ids:
        return []
    result = await session.execute(
        select(ReviewCycle).where(ReviewCycle.project_id.in_(project_ids), ReviewCycle.year == year)
    )
    return list(result.scalars().all())


async def get_cycle_assignments(session: AsyncSession, cycle_ids: list[str]) -> dict[str, list[ReviewCycleAssignment]]:
    mapping: dict[str, list[ReviewCycleAssignment]] = {cycle_id: [] for cycle_id in cycle_ids}
    if not cycle_ids:
        return mapping
    result = await session.execute(select(ReviewCycleAssignment).where(ReviewCycleAssignment.cycle_id.in_(cycle_ids)))
    for assignment in result.scalars().all():
        mapping[assignment.cycle_id].append(assignment)
    return mapping


async def get_cycle(session: AsyncSession, project_id: str, year: int, quarter: int) -> Optional[ReviewCycle]:
    result = await session.execute(
        select(ReviewCycle).where(
            ReviewCycle.project_id == project_id, ReviewCycle.year == year, ReviewCycle.quarter == quarter,
        )
    )
    return result.scalar_one_or_none()


async def create_cycle(
    session: AsyncSession, cycle_id: str, project_id: str, year: int, quarter: int,
    initiated_by: Optional[str], assignments: list[tuple[str, Optional[str]]],
) -> ReviewCycle:
    cycle = ReviewCycle(
        id=cycle_id, project_id=project_id, year=year, quarter=quarter,
        initiated_by=initiated_by, initiated_at=datetime.now(timezone.utc),
    )
    session.add(cycle)
    await session.flush()
    for platform, reviewer_id in assignments:
        session.add(ReviewCycleAssignment(cycle_id=cycle_id, platform=platform, reviewer_id=reviewer_id))
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def get_users_by_ids(session: AsyncSession, user_ids: list[str]) -> dict[str, User]:
    ids = [user_id for user_id in set(user_ids) if user_id]
    if not ids:
        return {}
    result = await session.execute(select(User).where(User.id.in_(ids)))
    return {user.id: user for user in result.scalars().all()}


async def get_first_review_dates(session: AsyncSession, project_ids: list[str]) -> dict[str, datetime]:
    """Earliest non-errored review per project (reviews can predate the project record)."""
    if not project_ids:
        return {}
    result = await session.execute(
        select(PlatformReview.project_id, func.min(PlatformReview.created_at))
        .where(PlatformReview.project_id.in_(project_ids), PlatformReview.status != "error")
        .group_by(PlatformReview.project_id)
    )
    return {project_id: first for project_id, first in result.all()}


# --- automated cycle reviews ---

async def get_cycle_by_id(session: AsyncSession, cycle_id: str) -> Optional[ReviewCycle]:
    return await session.get(ReviewCycle, cycle_id)


async def get_assignment(session: AsyncSession, cycle_id: str, platform: str) -> Optional[ReviewCycleAssignment]:
    return await session.get(ReviewCycleAssignment, (cycle_id, platform))


async def update_assignment(session: AsyncSession, assignment: ReviewCycleAssignment, **fields) -> ReviewCycleAssignment:
    for name, value in fields.items():
        setattr(assignment, name, value)
    await session.commit()
    await session.refresh(assignment)
    return assignment


_QUEUE_ORDER = (ReviewCycleAssignment.queued_at, ReviewCycleAssignment.cycle_id, ReviewCycleAssignment.platform)


async def list_queued_keys(session: AsyncSession) -> list[tuple[str, str]]:
    result = await session.execute(
        select(ReviewCycleAssignment.cycle_id, ReviewCycleAssignment.platform)
        .where(ReviewCycleAssignment.run_status == "queued")
        .order_by(*_QUEUE_ORDER)
    )
    return [(cycle_id, platform) for cycle_id, platform in result.all()]


async def claim_next_queued(session: AsyncSession) -> Optional[ReviewCycleAssignment]:
    result = await session.execute(
        select(ReviewCycleAssignment).where(ReviewCycleAssignment.run_status == "queued").order_by(*_QUEUE_ORDER).limit(1)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        return None
    return await update_assignment(
        session, assignment, run_status="running", started_at=datetime.now(timezone.utc),
        attempts=(assignment.attempts or 0) + 1, run_phase=None, run_progress=0, run_error=None, failure_kind=None,
        cancel_requested=None,  # a stop/pause belongs to one run; never let a stale one kill this run
    )


async def requeue_assignments(session: AsyncSession, include_running: bool) -> int:
    condition = and_(ReviewCycleAssignment.run_status == "failed", ReviewCycleAssignment.failure_kind == "system")
    if include_running:
        condition = or_(condition, ReviewCycleAssignment.run_status == "running")
    result = await session.execute(
        update(ReviewCycleAssignment).where(condition).values(
            run_status="queued", queued_at=datetime.now(timezone.utc),
            run_error=None, failure_kind=None, run_phase=None, run_progress=None, cancel_requested=None,
        )
    )
    await session.commit()
    return result.rowcount


async def get_review_statuses(session: AsyncSession, review_ids: list[str]) -> dict[str, str]:
    ids = [review_id for review_id in set(review_ids) if review_id]
    if not ids:
        return {}
    result = await session.execute(select(PlatformReview.id, PlatformReview.status).where(PlatformReview.id.in_(ids)))
    return {review_id: status for review_id, status in result.all()}


async def list_open_cycles(session: AsyncSession, project_ids: Optional[set[str]]) -> list[ReviewCycle]:
    if project_ids is not None and not project_ids:
        return []
    open_cycle_ids = select(ReviewCycleAssignment.cycle_id).where(ReviewCycleAssignment.run_status != "completed")
    query = select(ReviewCycle).where(ReviewCycle.id.in_(open_cycle_ids))
    if project_ids is not None:
        query = query.where(ReviewCycle.project_id.in_(project_ids))
    result = await session.execute(query.order_by(ReviewCycle.initiated_at.desc()))
    return list(result.scalars().all())


async def get_assignment_by_review_id(session: AsyncSession, review_id: str) -> Optional[ReviewCycleAssignment]:
    result = await session.execute(select(ReviewCycleAssignment).where(ReviewCycleAssignment.review_id == review_id))
    return result.scalars().first()


async def add_notifications(session: AsyncSession, event: str, recipient_ids: list[str], payload: dict) -> None:
    now = datetime.now(timezone.utc)
    for recipient_id in recipient_ids:
        session.add(NotificationOutbox(
            id=str(uuid.uuid4()), event=event, recipient_user_id=recipient_id, payload=payload, created_at=now,
        ))
    await session.commit()


async def list_notifications(session: AsyncSession, event: Optional[str] = None) -> list[NotificationOutbox]:
    query = select(NotificationOutbox).order_by(NotificationOutbox.created_at, NotificationOutbox.recipient_user_id)
    if event:
        query = query.where(NotificationOutbox.event == event)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_active_user_ids_with_roles(session: AsyncSession, roles: frozenset[str]) -> list[str]:
    result = await session.execute(
        select(User.id).where(User.role.in_(roles), User.is_active.is_(True)).order_by(User.email)
    )
    return [user_id for (user_id,) in result.all()]


async def _org_settings_row(session: AsyncSession) -> OrgSettings:
    settings = await session.get(OrgSettings, _ORG_SETTINGS_ID)
    if settings is None:
        settings = OrgSettings(id=_ORG_SETTINGS_ID, default_llm_provider="ollama", updated_at=datetime.now(timezone.utc))
        session.add(settings)
    return settings


async def update_devops_pat(session: AsyncSession, encrypted: str, last4: str, user_id: str) -> OrgSettings:
    settings = await _org_settings_row(session)
    settings.devops_pat_encrypted = encrypted
    settings.devops_pat_last4 = last4
    settings.devops_pat_updated_at = datetime.now(timezone.utc)
    settings.devops_pat_updated_by = user_id
    await session.commit()
    await session.refresh(settings)
    return settings


async def update_auto_compile_modes(session: AsyncSession, modes: dict) -> OrgSettings:
    settings = await _org_settings_row(session)
    settings.auto_compile_modes = dict(modes)
    await session.commit()
    await session.refresh(settings)
    return settings


# --- review queue monitor ---

_QUEUE_STATE_ID = 1


async def get_queue_state(session: AsyncSession) -> ReviewQueueState:
    state = await session.get(ReviewQueueState, _QUEUE_STATE_ID)
    if state is None:
        state = ReviewQueueState(id=_QUEUE_STATE_ID, paused=False)
        session.add(state)
        await session.commit()
        await session.refresh(state)
    return state


async def set_queue_paused(session: AsyncSession, paused: bool, user_id: Optional[str]) -> ReviewQueueState:
    state = await get_queue_state(session)
    state.paused = paused
    state.paused_by = user_id if paused else None
    state.paused_at = datetime.now(timezone.utc) if paused else None
    await session.commit()
    await session.refresh(state)
    return state


async def list_assignments_with_status(
    session: AsyncSession, status: str, newest_finished_first: bool = False, limit: Optional[int] = None,
) -> list[ReviewCycleAssignment]:
    query = select(ReviewCycleAssignment).where(ReviewCycleAssignment.run_status == status)
    query = query.order_by(ReviewCycleAssignment.finished_at.desc()) if newest_finished_first else query.order_by(*_QUEUE_ORDER)
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_assignments_with_status(session: AsyncSession, status: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(ReviewCycleAssignment).where(ReviewCycleAssignment.run_status == status)
    )
    return result.scalar_one()


async def front_of_queue_time(session: AsyncSession) -> datetime:
    """A queued_at that sorts before every queued item."""
    result = await session.execute(
        select(func.min(ReviewCycleAssignment.queued_at)).where(ReviewCycleAssignment.run_status == "queued")
    )
    earliest = result.scalar_one_or_none()
    return (earliest or datetime.now(timezone.utc)) - timedelta(seconds=1)

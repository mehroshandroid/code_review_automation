import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClauseChecklist, OrgSettings, PlatformReview, Project, SampleTemplate


async def create_project(session: AsyncSession, project_id: str, name: str) -> Project:
    project = Project(id=project_id, name=name, created_at=datetime.now(timezone.utc))
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def list_projects(session: AsyncSession) -> list[Project]:
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


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
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review


async def get_review_by_id(session: AsyncSession, review_id: str) -> Optional[PlatformReview]:
    return await session.get(PlatformReview, review_id)


async def list_reviews_for_project(session: AsyncSession, project_id: str) -> list[PlatformReview]:
    result = await session.execute(
        select(PlatformReview)
        .where(PlatformReview.project_id == project_id)
        .order_by(PlatformReview.created_at.desc())
    )
    return list(result.scalars().all())


async def list_reviews(
    session: AsyncSession,
    year: int,
    platform: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[PlatformReview]:
    query = select(PlatformReview).where(extract("year", PlatformReview.created_at) == year)
    if platform:
        query = query.where(PlatformReview.platform.ilike(platform))
    if project_id:
        query = query.where(PlatformReview.project_id == project_id)
    query = query.order_by(PlatformReview.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_review_years(session: AsyncSession) -> list[int]:
    result = await session.execute(select(extract("year", PlatformReview.created_at)).distinct())
    return sorted({int(year) for (year,) in result.all()})


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

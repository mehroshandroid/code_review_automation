import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.db import crud
from app.db.session import new_session

router = APIRouter()

DEFAULT_LLM_PROVIDER = "ollama"


def _sample_templates_dir() -> Path:
    return Path(os.environ.get("SAMPLE_TEMPLATES_DIR", "/data/sample-templates"))


class LlmProviderSettings(BaseModel):
    default_llm_provider: str
    default_ollama_model: str | None = None


class ClauseChecklistBody(BaseModel):
    checklist_text: str


@router.get("/api/settings/llm-provider")
async def get_llm_provider_settings():
    async with new_session() as session:
        settings = await crud.get_org_settings(session)
    if settings is None:
        return {"default_llm_provider": DEFAULT_LLM_PROVIDER, "default_ollama_model": None}
    return {"default_llm_provider": settings.default_llm_provider, "default_ollama_model": settings.default_ollama_model}


@router.put("/api/settings/llm-provider")
async def put_llm_provider_settings(body: LlmProviderSettings):
    async with new_session() as session:
        settings = await crud.update_org_settings(
            session, default_llm_provider=body.default_llm_provider, default_ollama_model=body.default_ollama_model
        )
    return {"default_llm_provider": settings.default_llm_provider, "default_ollama_model": settings.default_ollama_model}


def _checklist_to_dict(checklist) -> dict:
    return {"platform": checklist.platform, "sub_id": checklist.sub_id, "checklist_text": checklist.checklist_text}


@router.get("/api/settings/clause-checklists")
async def list_clause_checklists():
    async with new_session() as session:
        checklists = await crud.list_clause_checklists(session)
    return {"checklists": [_checklist_to_dict(c) for c in checklists]}


@router.put("/api/settings/clause-checklists/{platform}/{sub_id}")
async def put_clause_checklist(platform: str, sub_id: str, body: ClauseChecklistBody):
    async with new_session() as session:
        checklist = await crud.upsert_clause_checklist(session, platform=platform, sub_id=sub_id, checklist_text=body.checklist_text)
    return _checklist_to_dict(checklist)


@router.delete("/api/settings/clause-checklists/{platform}/{sub_id}", status_code=204)
async def delete_clause_checklist(platform: str, sub_id: str):
    async with new_session() as session:
        deleted = await crud.delete_clause_checklist(session, platform=platform, sub_id=sub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checklist not found")
    return Response(status_code=204)


def _template_to_dict(template) -> dict:
    return {"platform": template.platform, "filename": template.filename, "uploaded_at": template.uploaded_at.isoformat()}


@router.get("/api/settings/sample-templates")
async def list_sample_templates():
    async with new_session() as session:
        templates = await crud.list_sample_templates(session)
    return {"templates": [_template_to_dict(t) for t in templates]}


@router.post("/api/settings/sample-templates/{platform}")
async def upload_sample_template(platform: str, file: UploadFile = File(...)):
    templates_dir = _sample_templates_dir()
    templates_dir.mkdir(parents=True, exist_ok=True)
    file_path = templates_dir / f"{platform}.xlsx"
    file_path.write_bytes(await file.read())

    async with new_session() as session:
        template = await crud.upsert_sample_template(
            session, platform=platform, filename=file.filename or f"{platform}.xlsx",
            file_path=str(file_path), uploaded_at=datetime.now(timezone.utc),
        )
    return _template_to_dict(template)


@router.delete("/api/settings/sample-templates/{platform}", status_code=204)
async def delete_sample_template(platform: str):
    async with new_session() as session:
        template = await crud.get_sample_template(session, platform)
        if template is None:
            raise HTTPException(status_code=404, detail="No sample template configured for this platform")
        Path(template.file_path).unlink(missing_ok=True)
        await crud.delete_sample_template(session, platform)
    return Response(status_code=204)

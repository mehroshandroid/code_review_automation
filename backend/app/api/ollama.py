from fastapi import APIRouter, Depends

from app.analyzer import ollama_client
from app.auth.permissions import require_permission

router = APIRouter()


@router.get("/api/ollama/models")
async def list_ollama_models(user=Depends(require_permission("reviews.create", "settings.manage"))):
    return {"models": await ollama_client.list_models()}

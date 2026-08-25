from fastapi import APIRouter, Depends

from app.analyzer import ollama_client
from app.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/api/ollama/models")
async def list_ollama_models(user=Depends(get_current_user)):
    return {"models": await ollama_client.list_models()}

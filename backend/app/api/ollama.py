from fastapi import APIRouter

from app.analyzer import ollama_client

router = APIRouter()


@router.get("/api/ollama/models")
async def list_ollama_models():
    return {"models": await ollama_client.list_models()}

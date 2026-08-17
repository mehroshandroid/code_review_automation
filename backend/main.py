from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analyzer.openai_client import is_stub_mode
from app.api.chat import router as chat_router
from app.api.ollama import router as ollama_router
from app.api.projects import router as projects_router
from app.api.reviews import router as reviews_router
from app.api.settings import router as settings_router

load_dotenv()

app = FastAPI(title="Android Code Review Automation")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(reviews_router)
app.include_router(ollama_router)
app.include_router(projects_router)
app.include_router(settings_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "azure_openai_connected": not is_stub_mode()}

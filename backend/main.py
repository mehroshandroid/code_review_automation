import uuid
from contextlib import asynccontextmanager
from os import environ

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analyzer.openai_client import is_stub_mode
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.cycles import router as cycles_router
from app.api.ollama import router as ollama_router
from app.api.projects import router as projects_router
from app.api.quarterly import router as quarterly_router
from app.api.reviews import router as reviews_router
from app.api.settings import router as settings_router
from app.api.users import router as users_router
from app.auth.hashing import hash_password
from app.db import crud
from app.db.session import new_session
from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


async def _seed_admin_if_needed() -> None:
    admin_email = environ.get("ADMIN_EMAIL")
    admin_password = environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        logger.warning("ADMIN_EMAIL/ADMIN_PASSWORD not set -- skipping admin account seeding")
        return
    try:
        async with new_session() as session:
            if await crud.count_users(session) > 0:
                return
            await crud.create_user(
                session, user_id=str(uuid.uuid4()), email=admin_email,
                password_hash=hash_password(admin_password), role="admin",
            )
    except Exception:
        logger.exception("Failed to seed the admin account")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _seed_admin_if_needed()
    yield


app = FastAPI(title="CodeAssure", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(reviews_router)
app.include_router(ollama_router)
app.include_router(projects_router)
app.include_router(quarterly_router)
app.include_router(cycles_router)
app.include_router(settings_router)
app.include_router(users_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "azure_openai_connected": not is_stub_mode()}

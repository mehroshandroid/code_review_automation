from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.analyzer.openai_client import is_stub_mode
from app.auth.permissions import require_permission, visible_project_ids
from app.chatbot.agent import answer_question
from app.db.session import new_session

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("/api/chat")
async def chat(body: ChatRequest, user=Depends(require_permission("chat.use"))):
    if is_stub_mode():
        return {
            "answer": (
                "Chat isn't configured yet -- set AZURE_OPENAI_KEY (and "
                "OPENAI_API_BASE/OPENAI_DEPLOYMENT_NAME/OPENAI_API_VERSION) "
                "to enable it."
            ),
            "sources": [],
        }
    async with new_session() as session:
        project_ids = await visible_project_ids(session, user)
    history = [{"role": message.role, "content": message.content} for message in body.history]
    return await answer_question(body.message, history, project_ids=project_ids)

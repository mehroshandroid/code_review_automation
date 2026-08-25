from fastapi import APIRouter
from pydantic import BaseModel

from app.analyzer.openai_client import is_stub_mode
from app.chatbot.agent import answer_question

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("/api/chat")
async def chat(body: ChatRequest):
    if is_stub_mode():
        return {
            "answer": (
                "Chat isn't configured yet -- set AZURE_OPENAI_KEY (and "
                "OPENAI_API_BASE/OPENAI_DEPLOYMENT_NAME/OPENAI_API_VERSION) "
                "to enable it."
            ),
            "sources": [],
        }
    history = [{"role": message.role, "content": message.content} for message in body.history]
    return await answer_question(body.message, history)

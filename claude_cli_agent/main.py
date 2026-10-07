from fastapi import FastAPI
from pydantic import BaseModel

from app.claude_runner import run_claude

app = FastAPI(title="Claude CLI Agent")


class AskRequest(BaseModel):
    prompt: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask")
async def ask(body: AskRequest):
    return await run_claude(body.prompt)

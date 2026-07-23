from fastapi import FastAPI

from app.analyzer.openai_client import is_stub_mode

app = FastAPI(title="Android Code Review Automation")


@app.get("/api/health")
async def health():
    return {"status": "ok", "azure_openai_connected": not is_stub_mode()}

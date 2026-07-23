from dotenv import load_dotenv
from fastapi import FastAPI

from app.analyzer.openai_client import is_stub_mode
from app.api.reviews import router as reviews_router

load_dotenv()

app = FastAPI(title="Android Code Review Automation")
app.include_router(reviews_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "azure_openai_connected": not is_stub_mode()}

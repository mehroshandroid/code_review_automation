import os
from pathlib import Path

import httpx

DEFAULT_COMPILER_SERVICE_URL = "http://compiler:8000"
TIMEOUT_SECONDS = 300.0


async def check_compile_warnings(zip_path: Path) -> dict:
    base_url = os.environ.get("COMPILER_SERVICE_URL", DEFAULT_COMPILER_SERVICE_URL)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            with open(zip_path, "rb") as f:
                response = await client.post(
                    f"{base_url.rstrip('/')}/lint",
                    files={"project": ("project.zip", f, "application/zip")},
                )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, OSError):
        return {"status": "unavailable", "warning_count": None, "issues": []}

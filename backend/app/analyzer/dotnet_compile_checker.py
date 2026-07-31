import os
from pathlib import Path

import httpx

DEFAULT_DOTNET_COMPILER_SERVICE_URL = "http://dotnet-compiler:8000"
# Kept above dotnet_compiler's own BUILD_TIMEOUT_SECONDS (1440s) so the
# service always gets to return its own "timed out" result first, rather
# than this client's connection timing out first and masking it.
TIMEOUT_SECONDS = 1500.0


async def check_dotnet_build_warnings(zip_path: Path) -> dict:
    base_url = os.environ.get("DOTNET_COMPILER_SERVICE_URL", DEFAULT_DOTNET_COMPILER_SERVICE_URL)
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

import os
from pathlib import Path

import httpx

DEFAULT_MAC_BUILD_AGENT_URL = "http://host.docker.internal:8100"
# Kept above mac_build_agent's own GRADLE_TIMEOUT_SECONDS (1440s) so the
# agent always gets to return its own "timed out" result first, rather
# than this client's connection timing out first and masking it.
TIMEOUT_SECONDS = 1500.0


async def check_android_local_warnings(zip_path: Path) -> dict:
    base_url = os.environ.get("MAC_BUILD_AGENT_URL", DEFAULT_MAC_BUILD_AGENT_URL)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            with open(zip_path, "rb") as f:
                response = await client.post(
                    f"{base_url.rstrip('/')}/android-lint",
                    files={"project": ("project.zip", f, "application/zip")},
                )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, OSError):
        return {"status": "unavailable", "warning_count": None, "issues": []}

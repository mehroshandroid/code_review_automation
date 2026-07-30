import re

import httpx

REPO_URL_RE = re.compile(r"^https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)/?$")


def parse_repo_url(url: str) -> dict | None:
    """Extracts {organization, project, repository} from an Azure DevOps repo
    URL of the form https://dev.azure.com/{org}/{project}/_git/{repo}.
    Returns None if the URL doesn't match this shape.
    """
    match = REPO_URL_RE.match(url.strip())
    if not match:
        return None
    organization, project, repository = match.groups()
    return {"organization": organization, "project": project, "repository": repository}


async def fetch_repo_zip(repo_url: str, pat: str, branch: str | None = None) -> dict:
    """Downloads the given Azure DevOps repo (optionally at a specific branch)
    as a zip archive via one authenticated GET to the Items REST API -- no
    git binary needed. Returns {"status": "ok"|"invalid_url"|"unauthorized"|
    "not_found"|"error", "content": bytes|None, "message": str|None}. The PAT
    is used only for this one request's Basic auth header -- it never appears
    in the return value, in an exception message, or in a log line.
    """
    parsed = parse_repo_url(repo_url)
    if parsed is None:
        return {"status": "invalid_url", "content": None, "message": "Not a recognized Azure DevOps repo URL."}

    url = (
        f"https://dev.azure.com/{parsed['organization']}/{parsed['project']}"
        f"/_apis/git/repositories/{parsed['repository']}/items"
        "?path=/&download=true&$format=zip&api-version=7.0&recursionLevel=full"
    )
    if branch:
        url += f"&versionDescriptor.version={branch}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, auth=("", pat))
        if response.status_code == 401:
            return {"status": "unauthorized", "content": None, "message": "Invalid PAT or insufficient permissions."}
        if response.status_code == 404:
            return {"status": "not_found", "content": None, "message": "Repository or branch not found."}
        response.raise_for_status()
        return {"status": "ok", "content": response.content, "message": None}
    except httpx.HTTPError:
        return {"status": "error", "content": None, "message": "Could not reach Azure DevOps."}

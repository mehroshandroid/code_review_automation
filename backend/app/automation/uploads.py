"""Source zips uploaded for quarterly cycle reviews (code hosted on a client's DevOps).

Kept only until the review is approved, so Retry/Re-run can reuse them.
"""
import os
import re
import shutil
import zipfile
from pathlib import Path

MAX_ZIP_BYTES = 500 * 1024 * 1024
_CHUNK = 1024 * 1024
_PLATFORM_SLUGS = {"Android": "android", "iOS": "ios", ".NET": "dotnet"}


class UploadError(ValueError):
    pass


def uploads_dir() -> Path:
    return Path(os.environ.get("CYCLE_UPLOADS_DIR", "/data/cycle-uploads"))


def _zip_path_for(cycle_id: str, platform: str) -> Path:
    slug = _PLATFORM_SLUGS.get(platform) or re.sub(r"[^a-z0-9]+", "-", platform.lower())
    return uploads_dir() / cycle_id / f"{slug}.zip"


async def save_zip(upload, cycle_id: str, platform: str) -> Path:
    if not (upload.filename or "").lower().endswith(".zip"):
        raise UploadError("Please upload a .zip file.")
    target = _zip_path_for(cycle_id, platform)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".uploading")
    size = 0
    too_large = False
    with partial.open("wb") as out:
        while chunk := await upload.read(_CHUNK):
            size += len(chunk)
            if size > MAX_ZIP_BYTES:
                too_large = True
                break
            out.write(chunk)
    if too_large:
        partial.unlink(missing_ok=True)
        raise UploadError("The zip is too large (max 500 MB).")
    if not zipfile.is_zipfile(partial):
        partial.unlink(missing_ok=True)
        raise UploadError("That file isn't a valid zip archive.")
    partial.replace(target)
    return target


def delete_zip(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)


def delete_cycle_uploads(cycle_ids) -> None:
    for cycle_id in cycle_ids:
        shutil.rmtree(uploads_dir() / cycle_id, ignore_errors=True)

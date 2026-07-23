import asyncio
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.analyzer.android_analyzer import analyze_project
from app.analyzer.excel_handler import aggregate_category_scores, populate_scores
from app.analyzer.openai_client import score_category
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

CATEGORIES = {
    "1": {"name": "Code naming conventions / Code Structure", "sub_criteria": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]},
    "2": {"name": "Reliability, Security & Observability", "sub_criteria": ["2.1", "2.2", "2.3", "2.4"]},
    "3": {"name": "Delivery Discipline & Architecture", "sub_criteria": ["3.1", "3.2", "3.3", "3.4"]},
    "4": {"name": "AI Usage & Code Ownership", "sub_criteria": ["4.1", "4.2", "4.3"]},
    "6": {"name": "Safe & Integrated AI Code", "sub_criteria": ["6.1", "6.2", "6.3"]},
}

_reviews: dict = {}


def _new_review_state() -> dict:
    return {
        "status": "processing",
        "phase": "pending",
        "progress": 0,
        "message": "Queued",
        "stats": {},
        "download_path": None,
        "error": None,
        "warnings": [],
        "test_coverage": None,
        "secrets_found": [],
    }


@router.post("/api/reviews")
async def create_review(androidZip: UploadFile = File(...), excelTemplate: UploadFile = File(...)):
    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"

    try:
        zip_path.write_bytes(await androidZip.read())
        template_path.write_bytes(await excelTemplate.read())
    except Exception as exc:
        logger.exception("Review %s failed while saving uploads", review_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        state = _new_review_state()
        state["status"] = "error"
        state["phase"] = "error"
        state["error"] = f"Failed to save uploaded files: {exc}"
        _reviews[review_id] = state
        return {"review_id": review_id, "status": "error"}

    zip_valid = (androidZip.filename or "").endswith(".zip")
    template_valid = (excelTemplate.filename or "").endswith(".xlsx")

    _reviews[review_id] = _new_review_state()
    asyncio.create_task(_run_review(review_id, work_dir, zip_path, template_path, zip_valid, template_valid))
    return {"review_id": review_id, "status": "processing"}


async def _run_review(
    review_id: str,
    work_dir: Path,
    zip_path: Path,
    template_path: Path,
    zip_valid: bool,
    template_valid: bool,
) -> None:
    state = _reviews[review_id]
    extract_dir = work_dir / "extracted"
    stats = {}
    try:
        if not zip_valid or not template_valid:
            state["status"] = "error"
            state["phase"] = "error"
            state["error"] = "androidZip must be a .zip file and excelTemplate must be a .xlsx file"
            return

        t0 = time.monotonic()
        state["phase"] = "extracting"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        stats["ingest_time_ms"] = int((time.monotonic() - t0) * 1000)
        state["progress"] = 20

        t1 = time.monotonic()
        state["phase"] = "analyzing"
        analysis = analyze_project(extract_dir)
        if analysis.fatal_error:
            state["status"] = "error"
            state["phase"] = "error"
            state["error"] = analysis.fatal_error
            return
        state["warnings"] = analysis.structure_warnings + [w["issue"] for w in analysis.version_warnings]
        state["test_coverage"] = analysis.test_coverage
        state["secrets_found"] = analysis.secrets_found
        stats["analysis_time_ms"] = int((time.monotonic() - t1) * 1000)
        state["progress"] = 50

        t2 = time.monotonic()
        state["phase"] = "scoring"
        scores_by_category = {}
        for category_id, category in CATEGORIES.items():
            sub_results = await score_category(category["name"], category["sub_criteria"], "")
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
        stats["scoring_time_ms"] = int((time.monotonic() - t2) * 1000)
        state["progress"] = 80

        t3 = time.monotonic()
        state["phase"] = "generating"
        output_path = work_dir / "output.xlsx"
        populate_scores(template_path, output_path, scores_by_category)
        stats["generation_time_ms"] = int((time.monotonic() - t3) * 1000)
        stats["total_time_ms"] = sum(stats.values())

        state["status"] = "completed"
        state["phase"] = "completed"
        state["progress"] = 100
        state["message"] = "Review complete"
        state["stats"] = stats
        state["download_path"] = str(output_path)
    except Exception as exc:
        logger.exception("Review %s failed", review_id)
        state["status"] = "error"
        state["phase"] = "error"
        state["error"] = str(exc)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        template_path.unlink(missing_ok=True)

import asyncio
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openpyxl import load_workbook
from starlette.background import BackgroundTask

from app.analyzer.android_analyzer import analyze_project, gather_code_context
from app.analyzer.compile_checker import check_compile_warnings
from app.analyzer.devops_client import fetch_repo_zip, parse_repo_url
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    discover_structure,
    generate_review_excel,
)
from app.analyzer.llm_client import generate_general_remarks, score_category
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

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
        "total_score_pct": None,
        "project_name": None,
        "category_scores": [],
        "code_context": None,
        "prompt_log": [],
        "lint_issues": [],
        "compile_status": None,
    }


def _compile_result_to_sub_score(compile_result: dict) -> dict:
    status = compile_result["status"]
    warning_count = compile_result["warning_count"]
    if status == "unavailable":
        return {"score": None, "remark": "Compile check unavailable (compiler service unreachable)."}
    if status == "build_failed":
        return {"score": 0, "remark": "Project failed to compile."}
    if warning_count == 0:
        return {"score": 1, "remark": "No Lint warnings or errors found."}
    return {"score": 0, "remark": f"{warning_count} Lint warning(s)/error(s) found."}


def _merge_compile_result_into_category_1(sub_results: dict, compile_sub_result: dict, categories: dict) -> dict:
    merged = {**sub_results, "1.4": compile_sub_result}
    return {sub_id: merged[sub_id] for sub_id in categories["1"]["sub_criteria"]}


@router.post("/api/reviews")
async def create_review(
    androidZip: UploadFile | None = File(None),
    excelTemplate: UploadFile = File(...),
    llmProvider: str = Form("azure"),
    ollamaModel: str | None = Form(None),
    compileCheckMode: str = Form("compiler"),
    platform: str = Form("Android"),
    devopsRepoUrl: str | None = Form(None),
    devopsPat: str | None = Form(None),
    devopsBranch: str | None = Form(None),
):
    review_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"

    has_zip = androidZip is not None
    has_devops = bool(devopsRepoUrl) and bool(devopsPat)

    if has_zip and has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."
    elif not has_zip and not has_devops:
        input_error = "Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."
    else:
        input_error = None

    if input_error:
        shutil.rmtree(work_dir, ignore_errors=True)
        state = _new_review_state()
        state["status"] = "error"
        state["phase"] = "error"
        state["message"] = "Review failed"
        state["error"] = input_error
        _reviews[review_id] = state
        return {"review_id": review_id, "status": "error"}

    try:
        if has_zip:
            zip_path.write_bytes(await androidZip.read())
        template_path.write_bytes(await excelTemplate.read())
    except Exception as exc:
        logger.exception("Review %s failed while saving uploads", review_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        state = _new_review_state()
        state["status"] = "error"
        state["phase"] = "error"
        state["message"] = "Review failed"
        state["error"] = f"Failed to save uploaded files: {exc}"
        _reviews[review_id] = state
        return {"review_id": review_id, "status": "error"}

    zip_valid = (androidZip.filename or "").endswith(".zip") if has_zip else True
    template_valid = (excelTemplate.filename or "").endswith(".xlsx")

    if has_zip:
        project_name = Path(androidZip.filename).stem if androidZip.filename else "Unknown Project"
    else:
        parsed = parse_repo_url(devopsRepoUrl)
        project_name = parsed["repository"] if parsed else "Unknown Project"

    state = _new_review_state()
    state["project_name"] = project_name
    _reviews[review_id] = state
    asyncio.create_task(
        _run_review(
            review_id, work_dir, zip_path, template_path, zip_valid, template_valid, project_name,
            llmProvider, ollamaModel, compileCheckMode, platform,
            devopsRepoUrl, devopsPat, devopsBranch,
        )
    )
    return {"review_id": review_id, "status": "processing"}


async def _run_review(
    review_id: str,
    work_dir: Path,
    zip_path: Path,
    template_path: Path,
    zip_valid: bool,
    template_valid: bool,
    project_name: str,
    llm_provider: str = "azure",
    ollama_model: str | None = None,
    compile_check_mode: str = "compiler",
    platform: str = "Android",
    devops_repo_url: str | None = None,
    devops_pat: str | None = None,
    devops_branch: str | None = None,
) -> None:
    state = _reviews[review_id]
    extract_dir = work_dir / "extracted"
    stats = {}
    try:
        if not zip_valid or not template_valid:
            state["status"] = "error"
            state["phase"] = "error"
            state["message"] = "Review failed"
            state["error"] = "androidZip must be a .zip file and excelTemplate must be a .xlsx file"
            return

        if devops_repo_url and devops_pat:
            t_fetch = time.monotonic()
            state["phase"] = "fetching"
            state["message"] = "Fetching repository from Azure DevOps..."
            fetch_result = await fetch_repo_zip(devops_repo_url, devops_pat, devops_branch)
            if fetch_result["status"] != "ok":
                state["status"] = "error"
                state["phase"] = "error"
                state["message"] = "Review failed"
                state["error"] = fetch_result["message"]
                return
            zip_path.write_bytes(fetch_result["content"])
            stats["fetch_time_ms"] = int((time.monotonic() - t_fetch) * 1000)

        t0 = time.monotonic()
        state["phase"] = "extracting"
        state["message"] = "Extracting project files..."
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        stats["ingest_time_ms"] = int((time.monotonic() - t0) * 1000)
        state["progress"] = 20

        t1 = time.monotonic()
        state["phase"] = "analyzing"
        state["message"] = "Analyzing project structure..."
        analysis = analyze_project(extract_dir)
        if analysis.fatal_error:
            state["status"] = "error"
            state["phase"] = "error"
            state["message"] = "Review failed"
            state["error"] = analysis.fatal_error
            return
        state["warnings"] = analysis.structure_warnings + [w["issue"] for w in analysis.version_warnings]
        state["test_coverage"] = analysis.test_coverage
        state["secrets_found"] = analysis.secrets_found
        code_context = gather_code_context(extract_dir)
        state["code_context"] = code_context
        template_ws = load_workbook(template_path).active
        categories, sub_criteria_descriptions = discover_structure(template_ws)
        state["category_scores"] = [
            {
                "id": category_id,
                "name": category["name"],
                "percent_points": None,
                "sub_criteria": [
                    {"id": sub_id, "description": sub_criteria_descriptions.get(sub_id), "score": None, "remark": None}
                    for sub_id in category["sub_criteria"]
                ],
            }
            for category_id, category in categories.items()
        ]
        stats["analysis_time_ms"] = int((time.monotonic() - t1) * 1000)
        state["progress"] = 35

        t1b = time.monotonic()
        state["phase"] = "compiling"
        if platform == "Android" and compile_check_mode != "static":
            state["message"] = "Compiling and running Lint checks..."
            compile_result = await check_compile_warnings(zip_path)
            state["lint_issues"] = compile_result["issues"]
            state["compile_status"] = compile_result["status"]
            compile_sub_result = _compile_result_to_sub_score(compile_result)
        else:
            state["message"] = (
                "Skipping compiler check (static analysis mode)..." if platform == "Android"
                else "Skipping compiler check (not applicable to this platform)..."
            )
            state["lint_issues"] = []
            state["compile_status"] = "skipped" if platform == "Android" else None
            compile_sub_result = None
        stats["compile_time_ms"] = int((time.monotonic() - t1b) * 1000)
        state["progress"] = 55

        t2 = time.monotonic()
        state["phase"] = "scoring"
        scores_by_category = {}
        category_count = len(categories)
        for index, (category_id, category) in enumerate(categories.items()):
            state["message"] = f"Evaluating {category['name']}..."
            llm_sub_criteria = (
                [sub_id for sub_id in category["sub_criteria"] if sub_id != "1.4"]
                if category_id == "1" and platform == "Android" and compile_check_mode == "compiler" else category["sub_criteria"]
            )
            sub_results, prompt_info = await score_category(
                llm_provider, category["name"], llm_sub_criteria, sub_criteria_descriptions, code_context,
                model=ollama_model, platform=platform,
            )
            if category_id == "1" and platform == "Android" and compile_check_mode == "compiler":
                sub_results = _merge_compile_result_into_category_1(sub_results, compile_sub_result, categories)
            scores_by_category[category_id] = aggregate_category_scores(sub_results)
            sub_scores = scores_by_category[category_id]["sub_scores"]
            for sub_entry in state["category_scores"][index]["sub_criteria"]:
                sub_result = sub_scores.get(sub_entry["id"])
                if sub_result is not None:
                    sub_entry["score"] = sub_result["score"]
                    sub_entry["remark"] = sub_result["remark"]
            state["category_scores"][index]["percent_points"] = scores_by_category[category_id]["percent_points"]
            state["prompt_log"].append(prompt_info)
            state["progress"] = 55 + int(30 * (index + 1) / category_count)
        stats["scoring_time_ms"] = int((time.monotonic() - t2) * 1000)
        state["total_score_pct"] = compute_total_score_pct(scores_by_category)

        t3 = time.monotonic()
        state["phase"] = "generating"
        state["message"] = "Generating overall summary..."
        general_remarks, remarks_prompt_info = await generate_general_remarks(
            llm_provider, scores_by_category, model=ollama_model, platform=platform
        )
        state["prompt_log"].append(remarks_prompt_info)
        state["progress"] = 95
        state["message"] = "Populating review document..."
        output_path = work_dir / "output.xlsx"
        generate_review_excel(
            template_path,
            output_path,
            scores_by_category,
            project_name=project_name,
            general_remarks=general_remarks,
            reviewer_name="Claude",
            review_date=date.today(),
        )
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
        state["message"] = "Review failed"
        state["error"] = str(exc)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        template_path.unlink(missing_ok=True)
        if state["download_path"] is None:
            shutil.rmtree(work_dir, ignore_errors=True)


@router.get("/api/reviews/{review_id}/progress")
async def get_progress(review_id: str):
    state = _reviews.get(review_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown review_id")
    return {
        "status": state["status"],
        "phase": state["phase"],
        "progress": state["progress"],
        "message": state["message"],
        "stats": state["stats"],
        "download_url": f"/api/reviews/{review_id}/download" if state["status"] == "completed" else None,
        "error": state["error"],
        "warnings": state.get("warnings", []),
        "test_coverage": state.get("test_coverage"),
        "secrets_found": state.get("secrets_found", []),
        "total_score_pct": state.get("total_score_pct"),
        "project_name": state.get("project_name"),
        "category_scores": state.get("category_scores", []),
        "code_context": state.get("code_context"),
        "prompt_log": state.get("prompt_log", []),
        "lint_issues": state.get("lint_issues", []),
        "compile_status": state.get("compile_status"),
    }


@router.get("/api/reviews/{review_id}/download")
async def download_review(review_id: str):
    state = _reviews.get(review_id)
    if state is None or state["download_path"] is None:
        raise HTTPException(status_code=404, detail="Result not available")
    path = Path(state["download_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result already downloaded or expired")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="review_result.xlsx",
        background=BackgroundTask(shutil.rmtree, path.parent, ignore_errors=True),
    )

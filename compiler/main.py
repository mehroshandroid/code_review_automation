import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile

from app.lint_parser import count_warnings, find_lint_report, parse_lint_report
from app.lint_runner import extract_zip, run_lint

app = FastAPI(title="Android Compile/Lint Service")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/lint")
async def lint(project: UploadFile = File(...)):
    work_dir = Path(tempfile.mkdtemp(prefix="lint_"))
    try:
        extract_zip(await project.read(), work_dir)
        await run_lint(work_dir)

        report_path = find_lint_report(work_dir)
        if report_path is None:
            return {"status": "build_failed", "warning_count": None, "issues": []}

        issues = parse_lint_report(report_path)
        return {"status": "ok", "warning_count": count_warnings(issues), "issues": issues}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

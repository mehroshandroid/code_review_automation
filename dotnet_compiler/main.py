import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile

from app.dotnet_build_parser import count_warnings, parse_build_output
from app.dotnet_build_runner import extract_zip, run_build

app = FastAPI(title=".NET Build/Lint Service")
logger = logging.getLogger("uvicorn.error")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/lint")
async def lint(project: UploadFile = File(...)):
    work_dir = Path(tempfile.mkdtemp(prefix="dotnet_lint_"))
    try:
        extract_zip(await project.read(), work_dir)
        run_result = await run_build(work_dir)
        logger.info(
            "dotnet build exited with code %s\n--- stdout ---\n%s\n--- stderr ---\n%s",
            run_result["returncode"], run_result["stdout"], run_result["stderr"],
        )

        combined_log = run_result["stdout"] + "\n" + run_result["stderr"]
        issues = parse_build_output(combined_log)

        if run_result["returncode"] != 0 and not issues:
            return {
                "status": "build_failed",
                "warning_count": None,
                "issues": [],
                "log": combined_log.strip()[-4000:],
            }

        return {"status": "ok", "warning_count": count_warnings(issues), "issues": issues}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

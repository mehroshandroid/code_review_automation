import io
import tempfile
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

import app.api.reviews as reviews_module
from app.api.reviews import _new_review_state, _reviews, _run_review
from main import app

client = TestClient(app)


def _build_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("build.gradle", "android { compileSdkVersion 34 }")
        zf.writestr("AndroidManifest.xml", "<manifest />")
        zf.writestr("src/main/java/Main.java", "class Main {}")
    return buffer.getvalue()


def _build_ios_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.xcodeproj/project.pbxproj", "buildSettings = { SWIFT_VERSION = 5.9; };")
        zf.writestr("Info.plist", "<plist></plist>")
        zf.writestr("MyApp/AppDelegate.swift", "class AppDelegate {}")
    return buffer.getvalue()


def _build_dotnet_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.sln", "stub")
        zf.writestr(
            "MyApp/MyApp.csproj",
            "<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>",
        )
        zf.writestr("MyApp/Program.cs", "class Program {}")
    return buffer.getvalue()


def _build_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Clause", None, "Weight", "Avg Points", "Final Points", "% Points", "Remarks"])

    category_specs = [
        ("1", "Code naming conventions / Code Structure", 6),
        ("2", "Reliability, Security & Observability", 4),
        ("3", "Delivery Discipline & Architecture", 4),
        ("4", "AI Usage & Code Ownership", 3),
        ("6", "Safe & Integrated AI Code", 3),
    ]
    for category_id, name, sub_count in category_specs:
        category_row = ws.max_row + 1
        start_row = category_row + 1
        end_row = start_row + sub_count - 1
        ws.append([int(category_id), name, 1, f"=AVERAGE(D{start_row}:D{end_row})", None, None, None])
        for offset in range(1, sub_count + 1):
            ws.append([f"{category_id}.{offset}", f"Sub {category_id}.{offset}", None, None, None, None, None])
    wb.save(buffer)
    return buffer.getvalue()


def test_create_review_returns_id_and_creates_state(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "review_id" in body
        assert body["status"] == "processing"
        assert body["review_id"] in _reviews
        assert _reviews[body["review_id"]]["source"] == "upload"
        assert _reviews[body["review_id"]]["project_name"] == "project"


def test_create_review_write_failure_returns_200_with_error_state(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    created_tasks = []
    original_create_task = reviews_module.asyncio.create_task

    def _tracking_create_task(coro, *args, **kwargs):
        created_tasks.append(coro)
        return original_create_task(coro, *args, **kwargs)

    def _raise_write_bytes(self, data):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(reviews_module.asyncio, "create_task", _tracking_create_task)
    monkeypatch.setattr(Path, "write_bytes", _raise_write_bytes)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": ("template.xlsx", _build_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )

        # No exception propagated out of the endpoint; FastAPI still answers 200.
        assert response.status_code == 200
        body = response.json()
        assert "review_id" in body
        assert body["status"] == "error"

        review_id = body["review_id"]
        assert review_id in _reviews
        state = _reviews[review_id]
        assert state["status"] == "error"
        assert state["phase"] == "error"
        assert state["error"]

        # _run_review must never have been scheduled for this review.
        assert created_tasks == []


def test_create_review_returns_error_when_neither_zip_nor_devops_fields_provided(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        state = _reviews[body["review_id"]]
        assert state["error"] == "Provide either a project zip file or an Azure DevOps repo URL + PAT, not neither."


def test_create_review_returns_error_when_both_zip_and_devops_fields_provided(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={
                "devopsRepoUrl": "https://dev.azure.com/myorg/MyProject/_git/my-repo",
                "devopsPat": "fake-pat",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        state = _reviews[body["review_id"]]
        assert state["error"] == "Provide either a project zip file or an Azure DevOps repo URL + PAT, not both."


def test_create_review_with_devops_fields_derives_project_name_from_repo_url(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/reviews",
            files={
                "excelTemplate": (
                    "template.xlsx", _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={
                "devopsRepoUrl": "https://dev.azure.com/myorg/MyProject/_git/my-repo",
                "devopsPat": "fake-pat",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "processing"
        assert _reviews[body["review_id"]]["source"] == "devops"
        assert _reviews[body["review_id"]]["project_name"] == "my-repo"


async def test_run_review_removes_work_dir_when_no_output_produced():
    review_id = "leak-check-invalid-inputs"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(b"not really a zip")
    template_path.write_bytes(b"not really an xlsx")

    _reviews[review_id] = _new_review_state()

    # zip_valid=False takes the early-return error branch inside the try block,
    # so no output.xlsx is ever written and download_path stays None.
    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=False, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert state["status"] == "error"
    assert state["download_path"] is None
    assert not work_dir.exists()


async def test_run_review_updates_message_per_category_during_scoring(monkeypatch):
    review_id = "progress-message-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    seen_messages = []

    async def _recording_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        seen_messages.append(_reviews[review_id]["message"])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    assert seen_messages == [
        "Evaluating Code naming conventions / Code Structure...",
        "Evaluating Reliability, Security & Observability...",
        "Evaluating Delivery Discipline & Architecture...",
        "Evaluating AI Usage & Code Ownership...",
        "Evaluating Safe & Integrated AI Code...",
    ]

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert state["message"] == "Review complete"


async def test_run_review_updates_category_scores_progressively(monkeypatch):
    review_id = "category-scores-progress-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    # category_scores can't be seeded until the uploaded template is parsed
    # (categories are now discovered from it, not hardcoded).
    assert _reviews[review_id]["category_scores"] == []

    snapshots = []

    async def _recording_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        snapshots.append([(e["id"], e["percent_points"]) for e in _reviews[review_id]["category_scores"]])
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", _recording_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    # Snapshot taken right before each category is scored: by the time scoring
    # starts, category_scores has already been seeded (during analysis) with
    # all 5 discovered categories -- earlier categories show their resolved
    # percent_points, later ones are still None.
    assert snapshots[0] == [("1", None), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[1] == [("1", 100.0), ("2", None), ("3", None), ("4", None), ("6", None)]
    assert snapshots[4] == [("1", 100.0), ("2", 100.0), ("3", 100.0), ("4", 100.0), ("6", None)]

    final_scores = _reviews[review_id]["category_scores"]
    assert all(entry["percent_points"] == 100.0 for entry in final_scores)

    # Stub-style score_category above scores every LLM-scored sub-criterion 1
    # with an empty remark; every sub_criteria entry across every category
    # must reflect that (proves the per-category backfill runs for every
    # category, not just the first) -- except "1.4", which the compile-check
    # merge (_merge_compile_result_into_category_1) overwrites with its own
    # score/remark before scoring even runs, independent of score_category.
    for entry in final_scores:
        for sub in entry["sub_criteria"]:
            assert sub["score"] == 1
            if sub["id"] == "1.4":
                assert sub["remark"] == "No Lint warnings or errors found."
            else:
                assert sub["remark"] == ""


async def test_run_review_passes_llm_provider_and_model_through_to_scoring_calls(monkeypatch):
    review_id = "llm-provider-threading-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_providers = []
    captured_models = []

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_providers.append(provider)
        captured_models.append(model)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_generate_general_remarks(provider, category_results, model=None, platform="Android"):
        captured_providers.append(provider)
        captured_models.append(model)
        return "summary", {"label": "General remarks", "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "generate_general_remarks", fake_generate_general_remarks)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        llm_provider="ollama", ollama_model="qwen2.5-coder:7b",
    )

    # 5 category calls + 1 general-remarks call, all carrying the same provider/model.
    assert captured_providers == ["ollama"] * 6
    assert captured_models == ["qwen2.5-coder:7b"] * 6


async def test_run_review_uses_the_ollama_code_context_budget_for_ollama_reviews(monkeypatch):
    review_id = "ollama-code-context-budget-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_max_chars = []
    real_gather_code_context = reviews_module.android_analyzer.gather_code_context

    def fake_gather_code_context(extract_dir, max_chars=32000):
        captured_max_chars.append(max_chars)
        return real_gather_code_context(extract_dir, max_chars=max_chars)

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module.android_analyzer, "gather_code_context", fake_gather_code_context)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        llm_provider="ollama",
    )

    assert captured_max_chars == [reviews_module.CODE_CONTEXT_MAX_CHARS_OLLAMA]


async def test_run_review_uses_the_azure_code_context_budget_for_non_ollama_reviews(monkeypatch):
    review_id = "azure-code-context-budget-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_max_chars = []
    real_gather_code_context = reviews_module.android_analyzer.gather_code_context

    def fake_gather_code_context(extract_dir, max_chars=32000):
        captured_max_chars.append(max_chars)
        return real_gather_code_context(extract_dir, max_chars=max_chars)

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module.android_analyzer, "gather_code_context", fake_gather_code_context)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        llm_provider="azure",
    )

    assert captured_max_chars == [reviews_module.CODE_CONTEXT_MAX_CHARS_AZURE]


async def test_run_review_passes_platform_through_to_scoring_calls(monkeypatch):
    review_id = "platform-threading-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_ios_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_platforms = []

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_platforms.append(platform)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_generate_general_remarks(provider, category_results, model=None, platform="Android"):
        captured_platforms.append(platform)
        return "summary", {"label": "General remarks", "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "generate_general_remarks", fake_generate_general_remarks)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform="iOS",
    )

    # 5 category calls + 1 general-remarks call, all carrying the same platform.
    assert captured_platforms == ["iOS"] * 6


async def test_run_review_builds_prompt_log_and_code_context(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "prompt-log-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()
    assert _reviews[review_id]["code_context"] is None
    assert _reviews[review_id]["prompt_log"] == []

    async def _fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert "class Main {}" in state["code_context"]
    # 5 category calls + 1 general-remarks call, in that order.
    assert [entry["label"] for entry in state["prompt_log"]] == [
        "Code naming conventions / Code Structure",
        "Reliability, Security & Observability",
        "Delivery Discipline & Architecture",
        "AI Usage & Code Ownership",
        "Safe & Integrated AI Code",
        "General remarks",
    ]
    assert all(
        entry["tokens"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
        for entry in state["prompt_log"]
    )


def test_compile_result_to_sub_score_ok_zero_warnings():
    result = reviews_module._compile_result_to_sub_score({"status": "ok", "warning_count": 0, "issues": []})
    assert result == {"score": 1, "remark": "No Lint warnings or errors found."}


def test_compile_result_to_sub_score_ok_with_warnings():
    result = reviews_module._compile_result_to_sub_score({"status": "ok", "warning_count": 3, "issues": []})
    assert result == {"score": 0, "remark": "3 Lint warning(s)/error(s) found."}


def test_compile_result_to_sub_score_build_failed():
    result = reviews_module._compile_result_to_sub_score(
        {"status": "build_failed", "warning_count": None, "issues": []}
    )
    assert result == {"score": 0, "remark": "Project failed to compile."}


def test_compile_result_to_sub_score_unavailable():
    result = reviews_module._compile_result_to_sub_score(
        {"status": "unavailable", "warning_count": None, "issues": []}
    )
    assert result == {"score": None, "remark": "Compile check unavailable (compiler service unreachable)."}


def test_merge_compile_result_into_category_1_preserves_declared_order():
    llm_sub_results = {
        "1.1": {"score": 1, "remark": ""},
        "1.2": {"score": 1, "remark": ""},
        "1.3": {"score": 1, "remark": ""},
        "1.5": {"score": 1, "remark": ""},
        "1.6": {"score": 1, "remark": ""},
    }
    compile_sub_result = {"score": 0, "remark": "2 Lint warning(s)/error(s) found."}
    categories = {"1": {"name": "Code Structure", "sub_criteria": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]}}

    merged = reviews_module._merge_compile_result_into_category_1(llm_sub_results, compile_sub_result, categories)

    assert list(merged.keys()) == ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]
    assert merged["1.4"] == compile_sub_result


async def test_run_review_scores_1_4_from_compile_check_and_excludes_it_from_the_llm(monkeypatch):
    review_id = "compile-check-1-4"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_sub_criteria = {}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_compile_warnings(zip_path_arg):
        return {
            "status": "ok", "warning_count": 2,
            "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
        }

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    # "1.4" must never be sent to the LLM -- it's scored deterministically.
    assert "1.4" not in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "ok"
    assert state["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}]

    # Category 1: 5 LLM sub-criteria stubbed at score 1, plus 1.4 scored 0
    # (2 Lint warnings) -> (5*1 + 0) / 6 = 0.8333 -> rounds to 83.0%. Proves
    # the real 1.4 score is actually folded into the average, not dropped.
    assert state["category_scores"][0]["percent_points"] == 83.0


async def test_run_review_static_mode_skips_compiler_and_scores_1_4_via_llm(monkeypatch):
    review_id = "static-mode-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    compile_check_called = []
    captured_sub_criteria = {}

    async def fake_check_compile_warnings(zip_path_arg):
        compile_check_called.append(True)
        return {"status": "ok", "warning_count": 0, "issues": []}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": "stub"} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        compile_check_mode="static",
    )

    assert compile_check_called == []
    assert "1.4" in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "skipped"
    assert state["lint_issues"] == []
    sub_1_4 = next(s for s in state["category_scores"][0]["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 1
    assert sub_1_4["remark"] == "stub"


async def test_run_review_fetching_phase_writes_zip_from_devops_on_success(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "devops-fetch-success"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    async def fake_fetch_repo_zip(repo_url, pat, branch=None):
        return {"status": "ok", "content": _build_zip_bytes(), "message": None}

    async def fake_check_compile_warnings(zip_path_arg):
        return {"status": "ok", "warning_count": 0, "issues": []}

    monkeypatch.setattr(reviews_module, "fetch_repo_zip", fake_fetch_repo_zip)
    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="my-repo",
        devops_repo_url="https://dev.azure.com/myorg/MyProject/_git/my-repo", devops_pat="fake-pat",
    )

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert "fetch_time_ms" in state["stats"]


async def test_run_review_fetching_phase_failure_ends_review_with_devops_error_message(monkeypatch):
    review_id = "devops-fetch-failure"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    async def fake_fetch_repo_zip(repo_url, pat, branch=None):
        return {"status": "unauthorized", "content": None, "message": "Invalid PAT or insufficient permissions."}

    monkeypatch.setattr(reviews_module, "fetch_repo_zip", fake_fetch_repo_zip)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="my-repo",
        devops_repo_url="https://dev.azure.com/myorg/MyProject/_git/my-repo", devops_pat="secret-pat-value",
    )

    state = _reviews[review_id]
    assert state["status"] == "error"
    assert state["error"] == "Invalid PAT or insufficient permissions."
    assert "secret-pat-value" not in str(state)


async def test_run_review_updates_message_on_error_paths(monkeypatch):
    review_id = "progress-message-error-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(reviews_module.android_analyzer, "analyze_project", _boom)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    assert _reviews[review_id]["message"] == "Review failed"


async def test_run_review_removes_work_dir_on_unexpected_exception(monkeypatch):
    review_id = "leak-check-exception"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated analysis crash")

    monkeypatch.setattr(reviews_module.android_analyzer, "analyze_project", _boom)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test"
    )

    state = _reviews[review_id]
    assert state["status"] == "error"
    assert state["error"] == "simulated analysis crash"
    assert state["download_path"] is None
    assert not work_dir.exists()


async def test_run_review_unsupported_platform_skips_compile_check_entirely(monkeypatch):
    # Android, iOS, and .NET all have their own analyzer/compile-check
    # story now; a platform with none of those (e.g. Web (React), not yet
    # supported) must still get compile_status=None ("not applicable"),
    # not attempt either checker, and fall back to android_analyzer for
    # its (unused-for-scoring) structural analysis pass.
    review_id = "unsupported-platform-compile-check-skip"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    compile_check_called = []
    captured_sub_criteria = {}

    async def fake_check_compile_warnings(zip_path_arg):
        compile_check_called.append(True)
        return {"status": "ok", "warning_count": 0, "issues": []}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform="Web (React)",
    )

    assert compile_check_called == []
    # "1.4" is scored by the LLM like every other sub-criterion -- no exclusion.
    assert "1.4" in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] is None

    state = _reviews[review_id]
    assert state["compile_status"] is None
    assert state["lint_issues"] == []
    sub_1_4 = next(s for s in state["category_scores"][0]["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 1


async def test_run_review_uses_ios_analyzer_for_ios_platform(monkeypatch):
    # Forces the real (Azure) LLM client's own built-in stub mode for both
    # score_category and generate_general_remarks -- neither is monkeypatched
    # here, so without this, a real AZURE_OPENAI_KEY (loaded from the repo's
    # .env by main.py's load_dotenv() at import time) would trigger a real,
    # slow network call instead of the deterministic stub path.
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "ios-analyzer-dispatch-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MyApp.xcodeproj/project.pbxproj", "buildSettings = { SWIFT_VERSION = 5.9; };")
        zf.writestr("Info.plist", "<plist></plist>")
        zf.writestr("MyApp/AppDelegate.swift", "class AppDelegate {}")
    zip_path.write_bytes(buffer.getvalue())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="MyApp",
        platform="iOS",
    )

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert "AppDelegate.swift" in state["code_context"]


async def test_run_review_scores_1_4_from_ios_build_check_and_excludes_it_from_the_llm(monkeypatch):
    review_id = "ios-build-check-1-4"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_ios_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_sub_criteria = {}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_ios_build_warnings(zip_path_arg):
        return {
            "status": "ok", "warning_count": 2,
            "issues": [{"severity": "Warning", "message": "m", "file": "f.swift", "line": 1}],
        }

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_ios_build_warnings", fake_check_ios_build_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform="iOS",
    )

    # "1.4" must never be sent to the LLM -- it's scored deterministically.
    assert "1.4" not in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "ok"
    assert state["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.swift", "line": 1}]

    category_1 = next(c for c in state["category_scores"] if c["id"] == "1")
    sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 0
    assert sub_1_4["remark"] == "2 Lint warning(s)/error(s) found."


async def test_run_review_ios_static_mode_skips_build_check_and_scores_1_4_via_llm(monkeypatch):
    review_id = "ios-static-mode-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_ios_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    build_check_called = []
    captured_sub_criteria = {}

    async def fake_check_ios_build_warnings(zip_path_arg):
        build_check_called.append(True)
        return {"status": "ok", "warning_count": 0, "issues": []}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": "stub"} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "check_ios_build_warnings", fake_check_ios_build_warnings)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform="iOS", compile_check_mode="static",
    )

    assert build_check_called == []
    assert "1.4" in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "skipped"
    assert state["lint_issues"] == []
    category_1 = next(c for c in state["category_scores"] if c["id"] == "1")
    sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 1
    assert sub_1_4["remark"] == "stub"


async def test_run_review_android_local_mode_uses_local_checker_not_docker(monkeypatch):
    review_id = "android-local-mode-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    docker_checker_called = []
    captured_sub_criteria = {}

    async def fake_check_compile_warnings(zip_path_arg):
        docker_checker_called.append(True)
        return {"status": "ok", "warning_count": 0, "issues": []}

    async def fake_check_android_local_warnings(zip_path_arg):
        return {
            "status": "ok", "warning_count": 2,
            "issues": [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}],
        }

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "check_compile_warnings", fake_check_compile_warnings)
    monkeypatch.setattr(reviews_module, "check_android_local_warnings", fake_check_android_local_warnings)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        compile_check_mode="local",
    )

    # The Dockerized compiler must never be called in "local" mode.
    assert docker_checker_called == []
    assert "1.4" not in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "ok"
    assert state["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.java", "line": 1}]
    category_1 = next(c for c in state["category_scores"] if c["id"] == "1")
    sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 0
    assert sub_1_4["remark"] == "2 Lint warning(s)/error(s) found."


async def test_run_review_uses_dotnet_analyzer_for_dotnet_platform(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    review_id = "dotnet-analyzer-dispatch-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_dotnet_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="MyApp",
        platform=".NET",
    )

    state = _reviews[review_id]
    assert state["status"] == "completed"
    assert "Program.cs" in state["code_context"]
    # No dotnet-compiler service reachable in this test environment, so the
    # compile-check gracefully reports "unavailable" -- same fallback every
    # other checker gets when its service can't be reached.
    assert state["compile_status"] == "unavailable"


async def test_run_review_scores_1_4_from_dotnet_build_check_and_excludes_it_from_the_llm(monkeypatch):
    review_id = "dotnet-build-check-1-4"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_dotnet_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    captured_sub_criteria = {}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": ""} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    async def fake_check_dotnet_build_warnings(zip_path_arg):
        return {
            "status": "ok", "warning_count": 2,
            "issues": [{"severity": "Warning", "message": "m", "file": "f.cs", "line": 1}],
        }

    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)
    monkeypatch.setattr(reviews_module, "check_dotnet_build_warnings", fake_check_dotnet_build_warnings)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform=".NET",
    )

    # "1.4" must never be sent to the LLM -- it's scored deterministically.
    assert "1.4" not in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "ok"
    assert state["lint_issues"] == [{"severity": "Warning", "message": "m", "file": "f.cs", "line": 1}]

    category_1 = next(c for c in state["category_scores"] if c["id"] == "1")
    sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 0
    assert sub_1_4["remark"] == "2 Lint warning(s)/error(s) found."


async def test_run_review_dotnet_static_mode_skips_build_check_and_scores_1_4_via_llm(monkeypatch):
    review_id = "dotnet-static-mode-check"
    work_dir = Path(tempfile.mkdtemp(prefix=f"review_{review_id}_"))
    zip_path = work_dir / "android.zip"
    template_path = work_dir / "template.xlsx"
    zip_path.write_bytes(_build_dotnet_zip_bytes())
    template_path.write_bytes(_build_xlsx_bytes())

    _reviews[review_id] = _new_review_state()

    build_check_called = []
    captured_sub_criteria = {}

    async def fake_check_dotnet_build_warnings(zip_path_arg):
        build_check_called.append(True)
        return {"status": "ok", "warning_count": 0, "issues": []}

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android", checklists=None):
        captured_sub_criteria[category_name] = list(sub_criteria)
        sub_results = {sub_id: {"score": 1, "remark": "stub"} for sub_id in sub_criteria}
        prompt_info = {"label": category_name, "prompt_text": "stub", "tokens": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0,
        }}
        return sub_results, prompt_info

    monkeypatch.setattr(reviews_module, "check_dotnet_build_warnings", fake_check_dotnet_build_warnings)
    monkeypatch.setattr(reviews_module, "score_category", fake_score_category)

    await _run_review(
        review_id, work_dir, zip_path, template_path, zip_valid=True, template_valid=True, project_name="Test",
        platform=".NET", compile_check_mode="static",
    )

    assert build_check_called == []
    assert "1.4" in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] == "skipped"
    assert state["lint_issues"] == []
    category_1 = next(c for c in state["category_scores"] if c["id"] == "1")
    sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 1
    assert sub_1_4["remark"] == "stub"

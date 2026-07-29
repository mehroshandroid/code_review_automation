# Dynamic Category Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded, Android-specific `CATEGORIES` dict with category/sub-criteria structure discovered directly from whichever Excel template is uploaded, so the same review pipeline works for any platform's template without hardcoded knowledge.

**Architecture:** A new `discover_structure(ws)` in `excel_handler.py` detects category rows by their pre-existing `=AVERAGE(range)` rollup formula, reads the name from the description column, and synthesizes sub-criterion ids positionally from the formula's row range — replacing both `CATEGORIES` and `extract_sub_criteria_descriptions`. `reviews.py` calls it once the template is parsed (during the "analyzing" phase) instead of relying on a module constant known at import time. The Android-specific compile-check phase (real compiler call, clause `"1.4"` exclusion/merge) becomes conditional on `platform == "Android"`.

**Tech Stack:** FastAPI/Python backend (pytest, pytest-asyncio, openpyxl). No new dependencies (uses Python's built-in `re`).

## Global Constraints

- `discover_structure` synthesizes sub-criterion ids as `f"{category_id}.{n}"` (1-indexed by position within the category) — never reads them from the sheet's own id cells, which are already known to be unreliable (blank/typo'd/duplicated) in the real template.
- A category row is any row whose Avg Points cell holds a formula matching `=AVERAGE(<col><start>:<col><end>)` — this is the sole detection mechanism, with no other platform-specific assumptions.
- The compile-check phase (real compiler call, clause `"1.4"` exclusion from the LLM prompt, compile-result merge) only runs when `platform == "Android"`. For any other platform, `compile_status` stays `None` (not `"skipped"` — that value is reserved for Android's own static-analysis opt-out) and every discovered sub-criterion is scored by the LLM with no exclusion.
- `_iter_positional_sub_rows` and `populate_scores` in `excel_handler.py` are unchanged — they already derive their row counts from whatever `category_results` dict they're handed, regardless of where that dict's ids came from.
- TDD throughout: write the failing test, run it and confirm the failure, implement, run again and confirm the pass, then commit.

---

## Task 1: `discover_structure(ws)` in `excel_handler.py`

**Files:**
- Modify: `backend/app/analyzer/excel_handler.py`
- Modify: `backend/tests/test_excel_handler.py`

**Interfaces:**
- Consumes: `_find_header_row(ws)`, `_resolve_columns(ws, header_row)`, `_normalize_id(value)`, `_is_formula_cell(cell)` (all existing, unchanged).
- Produces: `discover_structure(ws) -> tuple[dict, dict]` returning `(categories, descriptions)` — `categories` shaped `{category_id: {"name": str, "sub_criteria": [sub_id, ...]}}` (identical shape to today's `CATEGORIES`), `descriptions` shaped `{sub_id: str}` (identical shape to today's `extract_sub_criteria_descriptions` output). `extract_sub_criteria_descriptions` itself is left untouched in this task — Task 2 migrates its only caller off it, and Task 3 removes it.

This task also fixes a latent inconsistency in the existing `_build_template()` test fixture, exposed by writing a real formula-range parser against it for the first time: its category row's formula reads `=AVERAGE(D3:D4)`, which incorrectly includes the category row's own cell (row 3) in the range — a real template's rollup formula would never do this. The two sub-criterion rows are actually rows 4 and 5, so the correct formula is `=AVERAGE(D4:D5)`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_excel_handler.py`, add the import:

```python
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    discover_structure,
    extract_sub_criteria_descriptions,
    generate_review_excel,
    populate_metadata,
    populate_scores,
)
```

Fix `_build_template()`'s formula (this is a pre-existing fixture bug, not a new requirement — its two sub-rows are rows 4 and 5, so the category row's rollup range should be `D4:D5`, not the self-including `D3:D4`):

```python
    ws.append([1, "Code naming conventions / Code Structure", 1, "=AVERAGE(D4:D5)", "=D3*C3", "=E3/C3", None])
```

Update the one existing assertion that checks this exact formula text, in `test_populate_scores_writes_sub_row_scores_positionally`:

```python
    assert category_row[3].value == "=AVERAGE(D4:D5)"
```

Add two new tests, after `test_extract_sub_criteria_descriptions_against_the_real_sample_template` (the last test in the file):

```python
def test_discover_structure_reads_categories_and_descriptions_positionally(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    _build_template(template_path)
    ws = load_workbook(template_path).active

    categories, descriptions = discover_structure(ws)

    assert categories == {
        "1": {"name": "Code naming conventions / Code Structure", "sub_criteria": ["1.1", "1.2"]},
    }
    assert descriptions == {
        "1.1": "Clear and consistent naming",
        "1.2": "Clean structure and formatting",
    }


def test_discover_structure_against_the_real_sample_template():
    """Proves discover_structure reproduces, purely by parsing the sheet, the
    exact same category/sub-criteria structure the old hardcoded CATEGORIES
    dict encoded for this template -- including category 4's positionally-
    synthesized ids despite its rows being labeled 4.2/4.3/4.3 in the sheet's
    own id column.
    """
    ws = load_workbook(FIXTURES_DIR / "SampleCodeReview.xlsx").active

    categories, descriptions = discover_structure(ws)

    assert categories == {
        "1": {"name": "Code naming conventions/ Code Structure", "sub_criteria": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]},
        "2": {"name": "Reliability, Security & Observability", "sub_criteria": ["2.1", "2.2", "2.3", "2.4"]},
        "3": {"name": "Delivery Discipline & Architecture", "sub_criteria": ["3.1", "3.2", "3.3", "3.4"]},
        "4": {"name": "AI Usage & Code Ownership", "sub_criteria": ["4.1", "4.2", "4.3"]},
        "6": {"name": "Safe & Integrated AI Code", "sub_criteria": ["6.1", "6.2", "6.3"]},
    }
    assert descriptions["1.1"] == "Clear and consistent naming conventions"
    assert descriptions["1.4"] == "No compile-time warnings"
    assert descriptions["2.4"] == "Keystore information should be stored in env. Or gradle"
    assert descriptions["4.1"] == "AI usage declared in PR comments along with tool name  (e.g., Copilot, ChatGPT, Azure OpenAI)"
    assert descriptions["4.3"] == "No unexplained or uncommented complex logic, No blind copy-paste"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_excel_handler.py -v`
Expected: FAIL — `ImportError: cannot import name 'discover_structure'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/analyzer/excel_handler.py`, add the `re` import at the top:

```python
import datetime
import re
from pathlib import Path
```

Add `discover_structure`, placed after `_iter_positional_sub_rows` and before `populate_scores`:

```python
AVERAGE_FORMULA_RE = re.compile(r"=AVERAGE\([A-Z]+(\d+):[A-Z]+(\d+)\)", re.IGNORECASE)


def discover_structure(ws) -> tuple[dict, dict]:
    """Discovers the full category/sub-criteria structure directly from the
    template, with no hardcoded platform-specific knowledge: a category row
    is any row whose Avg Points cell holds a pre-existing =AVERAGE(range)
    rollup formula (every real template's convention, regardless of
    platform); the formula's own row range tells us exactly how many
    sub-criterion rows follow and where. Sub-criterion ids are synthesized
    positionally ("{category_id}.{n}") since sub-row id cells are already
    known to be unreliable (blank/typo'd/duplicated) in real templates.
    Returns (categories, descriptions):
      categories: {category_id: {"name": str, "sub_criteria": [sub_id, ...]}}
      descriptions: {sub_id: str}
    """
    header_row = _find_header_row(ws)
    columns = _resolve_columns(ws, header_row)
    id_col = columns["id"]
    avg_col = columns["avg_points"]
    description_col = id_col + 1

    categories = {}
    descriptions = {}
    max_row = ws.max_row
    row = header_row + 1
    while row <= max_row:
        avg_cell = ws.cell(row=row, column=avg_col)
        match = AVERAGE_FORMULA_RE.match(str(avg_cell.value)) if _is_formula_cell(avg_cell) else None
        if match:
            category_id = _normalize_id(ws.cell(row=row, column=id_col).value)
            name_cell = ws.cell(row=row, column=description_col)
            category_name = str(name_cell.value).strip() if name_cell.value else ""
            start_row, end_row = int(match.group(1)), int(match.group(2))

            sub_ids = []
            for offset, sub_row in enumerate(range(start_row, end_row + 1), start=1):
                sub_id = f"{category_id}.{offset}"
                sub_ids.append(sub_id)
                desc_cell = ws.cell(row=sub_row, column=description_col)
                descriptions[sub_id] = str(desc_cell.value).strip() if desc_cell.value else ""

            categories[category_id] = {"name": category_name, "sub_criteria": sub_ids}
            row = end_row + 1
        else:
            row += 1
    return categories, descriptions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_excel_handler.py -v`
Expected: PASS — all tests green, including the two new ones and the corrected formula-text assertion.

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzer/excel_handler.py backend/tests/test_excel_handler.py
git commit -m "feat: add discover_structure to read categories/sub-criteria from the template"
```

---

## Task 2: Rewire `reviews.py` onto discovered structure, gate compile-check by platform

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/tests/test_reviews_create.py`
- Modify: `backend/tests/test_reviews_integration.py`

**Interfaces:**
- Consumes: `discover_structure(ws) -> (categories, descriptions)` (Task 1).
- Produces: `_new_review_state()`'s `category_scores` starts as `[]`. `_merge_compile_result_into_category_1(sub_results, compile_sub_result, categories)` — gains an explicit `categories` parameter. No public API changes (the `/api/reviews` and `/progress` endpoints are untouched).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_reviews_create.py`, replace `_build_xlsx_bytes()` with a version that includes real category rows (discovery has nothing to find in a bare header-only sheet):

```python
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
```

In `test_run_review_updates_category_scores_progressively`, replace the initial assertion block (the one deriving `expected_sub_criteria` from `reviews_module.CATEGORIES`) with:

```python
    # category_scores can't be seeded until the uploaded template is parsed
    # (categories are now discovered from it, not hardcoded).
    assert _reviews[review_id]["category_scores"] == []
```

Update the comment above the snapshot assertions to reflect the new seeding timing:

```python
    # Snapshot taken right before each category is scored: by the time scoring
    # starts, category_scores has already been seeded (during analysis) with
    # all 5 discovered categories -- earlier categories show their resolved
    # percent_points, later ones are still None.
```

(The snapshot assertions themselves — `snapshots[0]`, `snapshots[1]`, `snapshots[4]`, and everything after — are unchanged.)

Update `test_merge_compile_result_into_category_1_preserves_declared_order` for the new 3-argument signature:

```python
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
```

Add a new test at the end of the file, validating the platform gate:

```python
async def test_run_review_non_android_platform_skips_compile_check_entirely(monkeypatch):
    review_id = "non-android-compile-check-skip"
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

    async def fake_score_category(provider, category_name, sub_criteria, descriptions, code_snippets, model=None, platform="Android"):
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
        platform="iOS",
    )

    assert compile_check_called == []
    # "1.4" is scored by the LLM like every other sub-criterion -- no exclusion.
    assert "1.4" in captured_sub_criteria["Code naming conventions / Code Structure"]

    state = _reviews[review_id]
    assert state["compile_status"] is None
    assert state["lint_issues"] == []
    sub_1_4 = next(s for s in state["category_scores"][0]["sub_criteria"] if s["id"] == "1.4")
    assert sub_1_4["score"] == 1
```

In `backend/tests/test_reviews_integration.py`, fix the stale comment in `test_full_review_pipeline_in_stub_mode` (its fixture only ever had 2 categories, not 5 — the assertion itself is already correct regardless of category count, only the comment is wrong):

```python
        # Stub mode scores every sub-criterion 1 (perfect) across both
        # categories in this fixture, so each category's percent_points is
        # 100.0 and the mean across categories is exactly 100.0.
```

Add a new test at the end of the file:

```python
async def test_full_review_pipeline_non_android_platform_skips_compile_check(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    async def _fail_if_called(zip_path_arg):
        raise AssertionError("check_compile_warnings must not be called for a non-Android platform")

    monkeypatch.setattr(reviews_module, "check_compile_warnings", _fail_if_called)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reviews",
            files={
                "androidZip": ("project.zip", _build_zip_bytes(), "application/zip"),
                "excelTemplate": (
                    "template.xlsx",
                    _build_xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={"platform": "iOS"},
        )
        assert create_response.status_code == 200
        review_id = create_response.json()["review_id"]

        final_state = None
        for _ in range(50):
            progress_response = client.get(f"/api/reviews/{review_id}/progress")
            body = progress_response.json()
            if body["status"] in ("completed", "error"):
                final_state = body
                break
            time.sleep(0.05)

        assert final_state is not None, "review did not finish in time"
        assert final_state["status"] == "completed"
        assert final_state["compile_status"] is None
        assert final_state["lint_issues"] == []

        category_1 = next(c for c in final_state["category_scores"] if c["id"] == "1")
        sub_1_4 = next(s for s in category_1["sub_criteria"] if s["id"] == "1.4")
        # No compile-check exclusion for a non-Android platform -- 1.4 is
        # scored by the (stub-mode) LLM like every other sub-criterion.
        assert sub_1_4["score"] == 1
        assert "placeholder score" in sub_1_4["remark"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py tests/test_reviews_integration.py -v`
Expected: FAIL — `AttributeError`/`ImportError` on `reviews_module.CATEGORIES` (still referenced by the not-yet-updated `_new_review_state()`/`_run_review`), `TypeError: _merge_compile_result_into_category_1() takes 2 positional arguments but 3 were given`, and the new platform-gate tests fail since the compile-check phase isn't conditional yet.

- [ ] **Step 3: Implement**

In `backend/app/api/reviews.py`, update the imports:

```python
from app.analyzer.excel_handler import (
    aggregate_category_scores,
    compute_total_score_pct,
    discover_structure,
    generate_review_excel,
)
```

Delete the module-level `CATEGORIES` dict entirely.

Update `_new_review_state()`'s `category_scores` to start empty:

```python
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
```

Update `_merge_compile_result_into_category_1` to take `categories` explicitly:

```python
def _merge_compile_result_into_category_1(sub_results: dict, compile_sub_result: dict, categories: dict) -> dict:
    merged = {**sub_results, "1.4": compile_sub_result}
    return {sub_id: merged[sub_id] for sub_id in categories["1"]["sub_criteria"]}
```

Replace the description-extraction and category_scores-backfill block in `_run_review`'s analyzing phase:

```python
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
```

Replace the compiling-phase block with the platform-gated version:

```python
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
```

Update the scoring loop to iterate over the discovered `categories` and gate the exclusion/merge by platform:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_reviews_create.py tests/test_reviews_integration.py -v`
Expected: PASS — all tests in both files green, including the two new platform-gate tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: PASS — full backend suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reviews.py backend/tests/test_reviews_create.py backend/tests/test_reviews_integration.py
git commit -m "feat: discover categories from the template; gate compile-check by platform"
```

---

## Task 3: Remove `extract_sub_criteria_descriptions`

**Files:**
- Modify: `backend/app/analyzer/excel_handler.py`
- Modify: `backend/tests/test_excel_handler.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task only deletes now-dead code. `discover_structure` (Task 1) is the sole remaining way to read category/sub-criteria structure from a template.

- [ ] **Step 1: Confirm nothing else calls it**

Run: `cd backend && grep -rn "extract_sub_criteria_descriptions" --include="*.py" .`
Expected: only its own definition in `excel_handler.py` and its two tests in `test_excel_handler.py` — `reviews.py` was already migrated off it in Task 2.

- [ ] **Step 2: Remove the function and its tests**

Delete `extract_sub_criteria_descriptions` from `backend/app/analyzer/excel_handler.py`.

In `backend/tests/test_excel_handler.py`, remove `extract_sub_criteria_descriptions` from the import block, and delete its two tests: `test_extract_sub_criteria_descriptions_reads_positionally` and `test_extract_sub_criteria_descriptions_against_the_real_sample_template` (both fully superseded by Task 1's `discover_structure` tests, which assert the same facts).

- [ ] **Step 3: Run the full backend suite**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: PASS — full backend suite green, with a lower test count (2 fewer) reflecting the removed tests.

- [ ] **Step 4: Commit**

```bash
git add backend/app/analyzer/excel_handler.py backend/tests/test_excel_handler.py
git commit -m "refactor: remove extract_sub_criteria_descriptions, superseded by discover_structure"
```

---

## Final Verification

- [ ] Run the full backend suite: `cd backend && source venv/bin/activate && python -m pytest -v` — all green.
- [ ] Run the full frontend suite: `cd frontend && CI=true npx react-scripts test` — all green (this round is backend-only; confirms nothing broke).
- [ ] Rebuild and restart the backend container: `docker compose up -d --build backend`.
- [ ] Manually verify in the browser: run a real Android review end-to-end exactly as before — same categories, same clause 1.4 compile-check behavior, same report table — confirming the switch to sheet-driven discovery is invisible to the reviewer for the one platform that actually works today.

# Dynamic Category Discovery — Design Spec

**Status:** Approved
**Date:** 2026-07-30
**Source:** "moving forward lets thing generic solution for all the platforms, as much as resuability so, instead of hardcoding the sheet clauses, read the sheet and get them dynamically from the sheet, all of the platforms have similar formatting so it won't be an issue you can easilty wire it up with all platforms"

## Purpose

`CATEGORIES` in `backend/app/api/reviews.py` is a hardcoded dict describing the Android scoring template's exact structure (category ids, names, sub-criteria ids and counts). This ties the whole review pipeline to one specific template, which defeats the multi-platform architecture already built (landing page, `/review/:platform` routing, platform-aware prompts). Since every platform's template shares the same formatting convention — a category row carrying a pre-existing `=AVERAGE(range)` rollup formula, followed by that many sub-criterion rows — the entire category/sub-criteria structure can be discovered directly from whichever template is uploaded, with zero hardcoded, platform-specific knowledge. The same backend code then works for any platform's template without modification.

## Out of Scope

- Generalizing the compile-check business logic itself (which clause, if any, corresponds to "no compile warnings" for a non-Android platform) — deferred until a real second platform exists. This round only makes sure today's Android-specific compile-check logic doesn't silently misfire against a different template.
- Any change to the compiler microservice, the LLM clients, or the frontend beyond what's needed to keep existing behavior working.
- Any change to the Excel writing logic's positional-matching mechanism (`_iter_positional_sub_rows`, `populate_scores`) — it already derives its row counts from whatever `category_results` it's given, so it needs no changes at all.

## 1. `discover_structure(ws)` in `excel_handler.py`

Replaces both the hardcoded `CATEGORIES` dict and `extract_sub_criteria_descriptions`. Walks the sheet once, row by row after the header: whenever a row's Avg Points cell is a formula matching `=AVERAGE(<col><start>:<col><end>)`, that row is a category. Its id comes from the id column (same `_normalize_id` handling as today), its name from the description column (id column + 1), and the formula's row range gives the exact count and location of its sub-criteria — no need to know that count in advance. Each sub-criterion's id is synthesized positionally as `f"{category_id}.{n}"` (1-indexed) — never read from the sub-row's own id cell, since the existing test suite already proves those cells are unreliable in the real template (category 4's rows are labeled `4.2`/`4.3`/`4.3`, not `4.1`/`4.2`/`4.3`). Rows without a matching formula (blank rows, the trailing "Total" row, metadata rows) are simply skipped.

```python
import re

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

`extract_sub_criteria_descriptions` is removed (its only two call sites — `reviews.py` and its own tests — both move to `discover_structure`). `_iter_positional_sub_rows` and `populate_scores` are unchanged: they already take their row-count knowledge from whatever `category_results` dict they're handed, so they work identically regardless of whether that dict came from a hardcoded `CATEGORIES` or from `discover_structure`.

## 2. `reviews.py`: remove `CATEGORIES`, discover per-review, gate compile-check by platform

The module-level `CATEGORIES` dict is deleted. `_new_review_state()`'s `category_scores` starts as `[]` (it can no longer be seeded at creation time, since categories aren't known until the uploaded template is parsed).

In `_run_review`'s "analyzing" phase, immediately after loading the template worksheet:

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
```

This replaces both the old hardcoded seeding in `_new_review_state()` and the separate two-phase description backfill loop — descriptions are known the moment categories are discovered, so there's no need for a later backfill step.

The scoring loop iterates over the discovered `categories` (`for index, (category_id, category) in enumerate(categories.items())`) instead of the module constant; `category_count = len(categories)`.

The entire compile-check phase becomes conditional on platform:

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

The sub-criteria exclusion and merge in the scoring loop both add the same `platform == "Android"` guard:

```python
llm_sub_criteria = (
    [sub_id for sub_id in category["sub_criteria"] if sub_id != "1.4"]
    if category_id == "1" and platform == "Android" and compile_check_mode == "compiler" else category["sub_criteria"]
)
...
if category_id == "1" and platform == "Android" and compile_check_mode == "compiler":
    sub_results = _merge_compile_result_into_category_1(sub_results, compile_sub_result, categories)
```

`_merge_compile_result_into_category_1` gains an explicit `categories` parameter (it previously read the module-level `CATEGORIES["1"]["sub_criteria"]` directly):

```python
def _merge_compile_result_into_category_1(sub_results: dict, compile_sub_result: dict, categories: dict) -> dict:
    merged = {**sub_results, "1.4": compile_sub_result}
    return {sub_id: merged[sub_id] for sub_id in categories["1"]["sub_criteria"]}
```

For any platform other than `"Android"`, `compile_status` stays `None` (matching today's pre-review default, signaling "not applicable" rather than "skipped by choice"), no compiler call ever happens, and every discovered sub-criterion — including whatever lands at position 4 of category `"1"`, if that category even exists for that platform's template — is scored by the LLM like all the others.

## Testing

- **`excel_handler.py`**: new tests for `discover_structure` mirroring the existing `extract_sub_criteria_descriptions` tests — a synthetic template (blank first sub-row id, positional matching) and the real `SampleCodeReview.xlsx` fixture, asserting it reproduces exactly what `CATEGORIES` hardcodes today: 5 categories (`1,2,3,4,6`), matching names, sub-criteria counts (6/4/4/3/3), and the same descriptions `extract_sub_criteria_descriptions` already proves correct (including `4.1` = "AI usage declared in PR comments..." despite the sheet's own id cells reading `4.2/4.3/4.3`). The two existing `extract_sub_criteria_descriptions` tests are removed (function no longer exists).
- **`reviews.py`**: every test that builds a synthetic xlsx fixture and every reference to `reviews_module.CATEGORIES` gets reworked — fixtures need real category rows (id + name + `AVERAGE(range)` formula) since discovery has nothing to find otherwise. A new test confirms a non-Android platform's review never calls `check_compile_warnings` and scores every discovered sub-criterion (including category `"1"`'s 4th, if present) through the LLM with no exclusion.

## Ambiguity resolved during self-review

- A non-`"Android"` platform's `compile_status` is `None`, not `"skipped"` — `"skipped"` is reserved for Android's own static-analysis-mode opt-out (a deliberate choice within a platform that has a compiler), while `None` means "this platform has no compile-check concept at all," matching the field's existing pre-review default and keeping the two cases distinguishable in the API response.

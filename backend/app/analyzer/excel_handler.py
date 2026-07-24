import datetime
from pathlib import Path

from openpyxl import load_workbook

PLACEHOLDER_PROJECT_NAME = "<project name>"
GENERAL_REMARKS_PREFIX = "general remarks"
REVIEWERS_LABEL = "reviewers"
DATED_LABEL = "dated"

# The real template (samplefiles/SampleCodeReview.xlsx) has no separate "Score"
# column: category rows carry an existing =AVERAGE(...) formula in the
# "Avg Points" column, and that same column is reused to hold each
# sub-criterion's raw score directly. Sub-criteria are not reliably labeled in
# the id column (the first sub-row under each category is often blank, and
# labels can be duplicated/typo'd) -- the category's own AVERAGE(...) formula
# range is the actual source of truth for how many rows belong to it, so
# sub-rows are matched positionally (N rows immediately following the
# category row, N = number of sub-criteria for that category) rather than by
# reading their id cell.
HEADER_ALIASES = {
    "id": ["clause", "category", "sub-criterion", "sub criterion", "criterion"],
    "avg_points": ["avg points", "average points"],
    "remarks": ["remarks"],
}

MAX_HEADER_SCAN_ROWS = 10


def aggregate_category_scores(sub_scores: dict) -> dict:
    values = [v["score"] for v in sub_scores.values() if v.get("score") is not None]
    if not values:
        avg_points = final_points = percent_points = None
    else:
        avg_points = round(sum(values) / len(values), 2)
        final_points = avg_points
        percent_points = round(final_points * 100, 1)
    return {
        "avg_points": avg_points,
        "final_points": final_points,
        "percent_points": percent_points,
        "sub_scores": sub_scores,
    }


def _normalize_id(value):
    """Normalize an id cell's value to the string form used as category_results keys.

    Excel-native numeric cells come back from openpyxl as int/float rather than
    str. Whole-number floats (e.g. 1.0) are formatted without the trailing
    ".0" so they match string keys like "1". A blank cell normalizes to None.
    """
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _is_formula_cell(cell) -> bool:
    if cell.data_type == "f":
        return True
    return isinstance(cell.value, str) and cell.value.startswith("=")


def _set_cell(ws, row_idx: int, column: int, value) -> None:
    cell = ws.cell(row=row_idx, column=column)
    if _is_formula_cell(cell):
        return
    cell.value = value


def _find_header_row(ws) -> int:
    id_aliases = set(HEADER_ALIASES["id"])
    for row in ws.iter_rows(min_row=1, max_row=min(MAX_HEADER_SCAN_ROWS, ws.max_row)):
        for cell in row:
            if cell.value is not None and str(cell.value).strip().lower() in id_aliases:
                return cell.row
    raise ValueError(
        f"Could not find a header row (looked for one of {sorted(id_aliases)} "
        f"in the first {MAX_HEADER_SCAN_ROWS} rows)"
    )


def _resolve_columns(ws, header_row: int) -> dict:
    columns = {}
    for cell in ws[header_row]:
        if cell.value is None:
            continue
        header_text = str(cell.value).strip().lower()
        for key, aliases in HEADER_ALIASES.items():
            if header_text in aliases:
                columns[key] = cell.column
    missing = [key for key in HEADER_ALIASES if key not in columns]
    if missing:
        raise ValueError(f"Excel template missing expected columns: {missing}")
    return columns


def populate_scores(ws, category_results: dict) -> None:
    """Writes sub-criterion scores/remarks into an already-loaded worksheet, in place."""
    header_row = _find_header_row(ws)
    columns = _resolve_columns(ws, header_row)
    id_col = columns["id"]
    score_col = columns["avg_points"]
    remarks_col = columns["remarks"]

    max_row = ws.max_row
    row = header_row + 1
    while row <= max_row:
        id_cell = ws.cell(row=row, column=id_col)
        category_id = _normalize_id(id_cell.value)
        if category_id in category_results:
            sub_scores = category_results[category_id]["sub_scores"]
            offset = 1
            for sub in sub_scores.values():
                sub_row = row + offset
                if sub_row > max_row:
                    break
                _set_cell(ws, sub_row, score_col, sub.get("score"))
                _set_cell(ws, sub_row, remarks_col, sub.get("remark"))
                offset += 1
            row += offset
        else:
            row += 1


def populate_metadata(
    ws,
    project_name: str,
    general_remarks: str,
    reviewer_name: str,
    review_date: datetime.date,
) -> None:
    """Fills in the template's whole-review metadata cells (title, general
    remarks, reviewer, date), located by label text search rather than fixed
    coordinates so it tolerates minor row/column drift between template
    versions. Labels are matched case-insensitively; unmatched labels are
    left untouched (non-fatal -- a template missing one of these is still
    usable for scoring).
    """
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            text = cell.value.strip().lower()
            if text == PLACEHOLDER_PROJECT_NAME:
                _set_cell(ws, cell.row, cell.column, project_name)
            elif text.startswith(GENERAL_REMARKS_PREFIX):
                _set_cell(ws, cell.row, cell.column, f"General Remarks: {general_remarks}")
            elif text.startswith(REVIEWERS_LABEL):
                _set_cell(ws, cell.row, cell.column + 1, reviewer_name)
            elif text == DATED_LABEL:
                _set_cell(ws, cell.row, cell.column + 1, review_date)


def generate_review_excel(
    template_path: Path,
    output_path: Path,
    category_results: dict,
    project_name: str,
    general_remarks: str,
    reviewer_name: str = "Claude",
    review_date: datetime.date | None = None,
) -> None:
    wb = load_workbook(template_path)
    ws = wb.active
    populate_scores(ws, category_results)
    populate_metadata(
        ws,
        project_name=project_name,
        general_remarks=general_remarks,
        reviewer_name=reviewer_name,
        review_date=review_date or datetime.date.today(),
    )
    wb.save(output_path)

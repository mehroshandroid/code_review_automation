from pathlib import Path

from openpyxl import load_workbook

HEADER_ALIASES = {
    "id": ["category", "sub-criterion", "sub criterion", "criterion"],
    "avg_points": ["avg points", "average points"],
    "final_points": ["final points"],
    "percent_points": ["% points", "percent points"],
    "score": ["score"],
    "remarks": ["remarks"],
}


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


def _resolve_columns(ws) -> dict:
    columns = {}
    for cell in ws[1]:
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


def _normalize_id(value) -> str:
    """Normalize an id cell's value to the string form used as category_results keys.

    Excel-native numeric cells come back from openpyxl as int/float rather than
    str. Whole-number floats (e.g. 1.0) are formatted without the trailing
    ".0" so they match string keys like "1".
    """
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


def populate_scores(template_path: Path, output_path: Path, category_results: dict) -> None:
    wb = load_workbook(template_path)
    ws = wb.active
    columns = _resolve_columns(ws)

    for row in ws.iter_rows(min_row=2):
        id_cell = row[columns["id"] - 1]
        if id_cell.value is None:
            continue
        row_id = _normalize_id(id_cell.value)
        row_idx = id_cell.row

        if row_id in category_results:
            cat = category_results[row_id]
            _set_cell(ws, row_idx, columns["avg_points"], cat["avg_points"])
            _set_cell(ws, row_idx, columns["final_points"], cat["final_points"])
            _set_cell(ws, row_idx, columns["percent_points"], cat["percent_points"])
            continue

        for cat in category_results.values():
            sub = cat["sub_scores"].get(row_id)
            if sub is not None:
                _set_cell(ws, row_idx, columns["score"], sub.get("score"))
                _set_cell(ws, row_idx, columns["remarks"], sub.get("remark"))
                break

    wb.save(output_path)

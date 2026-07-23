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


def populate_scores(template_path: Path, output_path: Path, category_results: dict) -> None:
    wb = load_workbook(template_path)
    ws = wb.active
    columns = _resolve_columns(ws)

    for row in ws.iter_rows(min_row=2):
        id_cell = row[columns["id"] - 1]
        if id_cell.value is None:
            continue
        row_id = str(id_cell.value).strip()
        row_idx = id_cell.row

        if row_id in category_results:
            cat = category_results[row_id]
            ws.cell(row=row_idx, column=columns["avg_points"]).value = cat["avg_points"]
            ws.cell(row=row_idx, column=columns["final_points"]).value = cat["final_points"]
            ws.cell(row=row_idx, column=columns["percent_points"]).value = cat["percent_points"]
            continue

        for cat in category_results.values():
            sub = cat["sub_scores"].get(row_id)
            if sub is not None:
                ws.cell(row=row_idx, column=columns["score"]).value = sub.get("score")
                ws.cell(row=row_idx, column=columns["remarks"]).value = sub.get("remark")
                break

    wb.save(output_path)

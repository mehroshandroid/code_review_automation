from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.analyzer.excel_handler import aggregate_category_scores, populate_scores


def _build_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    headers = ["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    ws.append(["1", "Code naming conventions / Code Structure", None, None, None, None, None])
    ws.append(["1.1", "Clear and consistent naming", None, None, None, None, None])
    ws.append(["1.2", "Clean structure and formatting", None, None, None, None, None])
    wb.save(path)


def test_aggregate_category_scores_computes_mean_and_percent():
    sub_scores = {
        "1.1": {"score": 1, "remark": "Good naming"},
        "1.2": {"score": 0.5, "remark": "Some issues"},
    }
    result = aggregate_category_scores(sub_scores)
    assert result["avg_points"] == 0.75
    assert result["final_points"] == 0.75
    assert result["percent_points"] == 75.0
    assert result["sub_scores"] == sub_scores


def test_aggregate_category_scores_all_none_stays_none():
    sub_scores = {"1.1": {"score": None, "remark": ""}}
    result = aggregate_category_scores(sub_scores)
    assert result["avg_points"] is None
    assert result["final_points"] is None
    assert result["percent_points"] is None


def test_populate_scores_writes_values_and_preserves_formatting(tmp_path: Path):
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "output.xlsx"
    _build_template(template_path)

    category_results = {
        "1": aggregate_category_scores(
            {
                "1.1": {"score": 1, "remark": "Good naming"},
                "1.2": {"score": 0.5, "remark": "Some issues"},
            }
        )
    }
    populate_scores(template_path, output_path, category_results)

    wb = load_workbook(output_path)
    ws = wb.active

    header_row = [c.value for c in ws[1]]
    assert header_row == ["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"]
    assert ws["A1"].font.bold is True

    category_row = ws[2]
    assert category_row[3].value == 0.75
    assert category_row[4].value == 0.75
    assert category_row[5].value == 75.0

    sub_row_1_1 = ws[3]
    assert sub_row_1_1[2].value == 1
    assert sub_row_1_1[6].value == "Good naming"

    sub_row_1_2 = ws[4]
    assert sub_row_1_2[2].value == 0.5
    assert sub_row_1_2[6].value == "Some issues"


def test_populate_scores_raises_on_missing_columns(tmp_path: Path):
    template_path = tmp_path / "bad_template.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Description"])
    wb.save(template_path)

    output_path = tmp_path / "output.xlsx"
    try:
        populate_scores(template_path, output_path, {})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing" in str(exc).lower()


def test_populate_scores_preserves_formula_cells(tmp_path: Path):
    template_path = tmp_path / "formula_template.xlsx"
    output_path = tmp_path / "output.xlsx"

    wb = Workbook()
    ws = wb.active
    headers = ["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    ws.append(["1", "Code naming conventions / Code Structure", None, None, None, None, None])
    ws.append(["1.1", "Clear and consistent naming", None, None, None, None, None])
    ws.append(["1.2", "Clean structure and formatting", None, None, None, None, None])

    # Avg Points on the category row is formula-driven in this template.
    ws.cell(row=2, column=4, value="=1+1")
    wb.save(template_path)

    category_results = {
        "1": aggregate_category_scores(
            {
                "1.1": {"score": 1, "remark": "Good naming"},
                "1.2": {"score": 0.5, "remark": "Some issues"},
            }
        )
    }
    populate_scores(template_path, output_path, category_results)

    wb2 = load_workbook(output_path)
    ws2 = wb2.active

    category_row = ws2[2]
    # Formula cell must be left untouched.
    assert category_row[3].value == "=1+1"
    # Other cells in the same row are still populated normally.
    assert category_row[4].value == 0.75
    assert category_row[5].value == 75.0

    sub_row_1_1 = ws2[3]
    assert sub_row_1_1[2].value == 1
    assert sub_row_1_1[6].value == "Good naming"


def test_populate_scores_matches_excel_native_numeric_ids(tmp_path: Path):
    template_path = tmp_path / "numeric_ids_template.xlsx"
    output_path = tmp_path / "output.xlsx"

    wb = Workbook()
    ws = wb.active
    headers = ["Category", "Description", "Score", "Avg Points", "Final Points", "% Points", "Remarks"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    ws.append([None, "Code naming conventions / Code Structure", None, None, None, None, None])
    ws.cell(row=2, column=1, value=1)
    ws.append([None, "Clear and consistent naming", None, None, None, None, None])
    ws.cell(row=3, column=1, value=1.1)
    wb.save(template_path)

    category_results = {
        "1": aggregate_category_scores(
            {
                "1.1": {"score": 1, "remark": "Good naming"},
            }
        )
    }
    populate_scores(template_path, output_path, category_results)

    wb2 = load_workbook(output_path)
    ws2 = wb2.active

    category_row = ws2[2]
    assert category_row[3].value == 1.0
    assert category_row[4].value == 1.0
    assert category_row[5].value == 100.0

    sub_row_1_1 = ws2[3]
    assert sub_row_1_1[2].value == 1
    assert sub_row_1_1[6].value == "Good naming"

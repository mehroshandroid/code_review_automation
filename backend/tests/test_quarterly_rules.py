from datetime import date

import pytest

from app.quarterly import (
    TRACKED_PLATFORMS, can_initiate, canonical_platform, quarter_bounds, quarter_status, sort_platforms,
)

TODAY = date(2026, 10, 7)  # Q4 2026
CREATED = date(2025, 1, 1)
BOTH = ["Android", "iOS"]


def test_tracked_platforms():
    assert TRACKED_PLATFORMS == ("Android", "iOS", ".NET")


@pytest.mark.parametrize("raw,expected", [("android", "Android"), ("IOS", "iOS"), (".net", ".NET"), ("Web (React)", None), (None, None)])
def test_canonical_platform(raw, expected):
    assert canonical_platform(raw) == expected


def test_sort_platforms_uses_tracked_order():
    assert sort_platforms([".NET", "Android"]) == ["Android", ".NET"]


@pytest.mark.parametrize("quarter,start,end", [
    (1, date(2026, 1, 1), date(2026, 3, 31)),
    (2, date(2026, 4, 1), date(2026, 6, 30)),
    (3, date(2026, 7, 1), date(2026, 9, 30)),
    (4, date(2026, 10, 1), date(2026, 12, 31)),
])
def test_quarter_bounds(quarter, start, end):
    assert quarter_bounds(2026, quarter) == (start, end)


def test_done_when_every_platform_covered():
    assert quarter_status(CREATED, BOTH, {"Android", "iOS"}, False, 2026, 2, TODAY) == "done"


def test_done_even_for_current_quarter():
    assert quarter_status(CREATED, BOTH, {"Android", "iOS"}, False, 2026, 4, TODAY) == "done"


def test_overdue_when_past_incomplete_and_not_initiated():
    assert quarter_status(CREATED, BOTH, {"Android"}, False, 2026, 3, TODAY) == "overdue"
    assert quarter_status(CREATED, BOTH, set(), False, 2026, 1, TODAY) == "overdue"


def test_initiating_a_past_incomplete_quarter_makes_it_in_progress():
    assert quarter_status(CREATED, BOTH, {"Android"}, True, 2026, 3, TODAY) == "in_progress"
    assert quarter_status(CREATED, BOTH, set(), True, 2026, 1, TODAY) == "in_progress"


def test_initiated_quarter_still_becomes_done_when_covered():
    assert quarter_status(CREATED, BOTH, {"Android", "iOS"}, True, 2026, 3, TODAY) == "done"


def test_in_progress_with_cycle_or_partial_coverage():
    assert quarter_status(CREATED, BOTH, set(), True, 2026, 4, TODAY) == "in_progress"
    assert quarter_status(CREATED, BOTH, {"iOS"}, False, 2026, 4, TODAY) == "in_progress"


def test_not_started_current_quarter_with_nothing():
    assert quarter_status(CREATED, BOTH, set(), False, 2026, 4, TODAY) == "not_started"


def test_future_quarter_is_not_started():
    assert quarter_status(CREATED, BOTH, set(), False, 2027, 1, TODAY) == "not_started"


def test_last_day_of_quarter_is_not_overdue():
    assert quarter_status(CREATED, BOTH, {"Android"}, False, 2026, 3, date(2026, 9, 30)) == "in_progress"
    assert quarter_status(CREATED, BOTH, {"Android"}, False, 2026, 3, date(2026, 10, 1)) == "overdue"


def test_quarter_before_project_creation_is_not_applicable():
    assert quarter_status(date(2026, 8, 15), BOTH, set(), False, 2026, 2, TODAY) == "not_applicable"


def test_project_created_mid_quarter_is_tracked():
    assert quarter_status(date(2026, 8, 15), BOTH, set(), False, 2026, 3, TODAY) == "overdue"


def test_can_initiate():
    assert can_initiate("not_started", False, 2026, 4, TODAY) is True
    assert can_initiate("overdue", False, 2026, 2, TODAY) is True
    assert can_initiate("in_progress", False, 2026, 4, TODAY) is True
    assert can_initiate("in_progress", True, 2026, 4, TODAY) is False
    assert can_initiate("done", False, 2026, 2, TODAY) is False
    assert can_initiate("not_applicable", False, 2026, 1, TODAY) is False
    assert can_initiate("not_started", False, 2027, 1, TODAY) is False

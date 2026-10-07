"""Quarterly review rules: which quarter a date falls in, and a quarter's status.

A project's quarter is done once every platform it has received at least one
non-errored review dated inside that quarter (UTC).
"""
from datetime import date

TRACKED_PLATFORMS = ("Android", "iOS", ".NET")

_QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
_MONTH_END_DAY = {3: 31, 6: 30, 9: 30, 12: 31}
_INITIABLE = {"in_progress", "not_started", "overdue"}


def canonical_platform(value: str | None) -> str | None:
    if not value:
        return None
    for platform in TRACKED_PLATFORMS:
        if platform.lower() == value.strip().lower():
            return platform
    return None


def sort_platforms(platforms) -> list[str]:
    return sorted(set(platforms), key=TRACKED_PLATFORMS.index)


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    first_month, last_month = _QUARTER_MONTHS[quarter]
    return date(year, first_month, 1), date(year, last_month, _MONTH_END_DAY[last_month])


def quarter_status(
    project_created: date, platforms: list[str], covered: set[str], cycle_exists: bool,
    year: int, quarter: int, today: date,
) -> str:
    start, end = quarter_bounds(year, quarter)
    if end < project_created:
        return "not_applicable"
    if platforms and set(platforms) <= covered:
        return "done"
    if cycle_exists and today >= start:
        # Initiated (possibly after the quarter ended, to catch up): it's being worked on.
        return "in_progress"
    if today > end:
        return "overdue"
    if today >= start and covered:
        return "in_progress"
    return "not_started"


def is_late(status: str, year: int, quarter: int, today: date) -> bool:
    """An in-progress quarter whose calendar quarter has already ended."""
    _, end = quarter_bounds(year, quarter)
    return status == "in_progress" and today > end


def can_initiate(status: str, cycle_exists: bool, year: int, quarter: int, today: date) -> bool:
    start, _ = quarter_bounds(year, quarter)
    return not cycle_exists and today >= start and status in _INITIABLE

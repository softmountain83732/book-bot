# app/api/utils/semester.py
"""Academic semester mapping utilities shared between bot and Mini App API."""
from typing import Any


def format_semester(year: int, semester: Any) -> str:
    """Human-readable semester label respecting Year 2 mapping."""
    if year == 2:
        if semester == 3 or semester == "3":
            return "Semester 3"
        if semester == 4 or semester == "4":
            return "Semester 4"
        if semester in ("3 & 4",):
            return "Both (3 & 4)"
    else:
        if semester == 1 or semester == "1":
            return "Semester 1"
        if semester == 2 or semester == "2":
            return "Semester 2"
        if semester in ("1 & 2",):
            return "Both (1 & 2)"
    return str(semester)


def get_semester_options(year: int) -> list[dict]:
    """Return semester picker options for a given academic year."""
    if year == 2:
        return [
            {"value": "3", "label": "Semester 3"},
            {"value": "4", "label": "Semester 4"},
            {"value": "3 & 4", "label": "Both (3 & 4)"},
        ]
    return [
        {"value": "1", "label": "Semester 1"},
        {"value": "2", "label": "Semester 2"},
        {"value": "1 & 2", "label": "Both (1 & 2)"},
    ]


def build_semester_filter(year: int | None, semester_param: str | None) -> dict:
    """Build a MongoDB query fragment for semester filtering.

    Returns an empty dict when no semester filter is requested.
    Correctly handles Year 2 (semesters 3 & 4) vs all other years (1 & 2).
    """
    if not semester_param or semester_param == "all":
        return {}

    # Strip whitespace
    semester_param = semester_param.strip()

    # Both-semesters literal value passed directly
    if semester_param in ("1 & 2", "3 & 4"):
        return {"semester": semester_param}

    # Single semester digit strings
    if semester_param.isdigit():
        num = int(semester_param)
        if year == 2:
            both = "3 & 4"
        else:
            both = "1 & 2"
        return {"semester": {"$in": [num, both]}}

    return {}

# tests/test_semester.py
"""Tests for academic semester mapping utilities."""
import pytest
from app.api.utils.semester import build_semester_filter, format_semester, get_semester_options


def test_format_semester_year2_int():
    assert format_semester(2, 3) == "Semester 3"
    assert format_semester(2, 4) == "Semester 4"


def test_format_semester_year2_both():
    assert format_semester(2, "3 & 4") == "Both (3 & 4)"


def test_format_semester_year1_int():
    assert format_semester(1, 1) == "Semester 1"
    assert format_semester(1, 2) == "Semester 2"


def test_format_semester_year1_both():
    assert format_semester(1, "1 & 2") == "Both (1 & 2)"


def test_format_semester_other_years():
    assert format_semester(3, 1) == "Semester 1"
    assert format_semester(6, 2) == "Semester 2"
    assert format_semester(4, "1 & 2") == "Both (1 & 2)"


def test_semester_options_year2():
    opts = get_semester_options(2)
    values = [o["value"] for o in opts]
    assert values == ["3", "4", "3 & 4"]


def test_semester_options_year1():
    opts = get_semester_options(1)
    values = [o["value"] for o in opts]
    assert values == ["1", "2", "1 & 2"]


def test_semester_options_other_years():
    for yr in [3, 4, 5, 6]:
        opts = get_semester_options(yr)
        assert [o["value"] for o in opts] == ["1", "2", "1 & 2"]


def test_build_semester_filter_none():
    assert build_semester_filter(None, None) == {}
    assert build_semester_filter(1, None) == {}
    assert build_semester_filter(2, None) == {}


def test_build_semester_filter_all():
    assert build_semester_filter(1, "all") == {}
    assert build_semester_filter(2, "all") == {}


def test_build_semester_filter_year2_sem3():
    result = build_semester_filter(2, "3")
    assert result == {"semester": {"$in": [3, "3 & 4"]}}


def test_build_semester_filter_year2_sem4():
    result = build_semester_filter(2, "4")
    assert result == {"semester": {"$in": [4, "3 & 4"]}}


def test_build_semester_filter_year1_sem1():
    result = build_semester_filter(1, "1")
    assert result == {"semester": {"$in": [1, "1 & 2"]}}


def test_build_semester_filter_year1_sem2():
    result = build_semester_filter(1, "2")
    assert result == {"semester": {"$in": [2, "1 & 2"]}}


def test_build_semester_filter_both_literal_year2():
    result = build_semester_filter(2, "3 & 4")
    assert result == {"semester": "3 & 4"}


def test_build_semester_filter_both_literal_year1():
    result = build_semester_filter(1, "1 & 2")
    assert result == {"semester": "1 & 2"}

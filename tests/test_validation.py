# tests/test_validation.py
"""Comprehensive validation and edge case tests for book listing and seller rules."""
import pytest
from app.services.sell_service import validate_sell_input

def test_validate_sell_input_empty_title():
    valid, msg, _ = validate_sell_input(
        title="",
        major_slug="ceit",
        year=1,
        semester="1",
        price=10000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=["photo_1"],
    )
    assert valid is False
    assert "စာအုပ်အမည်" in msg

def test_validate_sell_input_too_short_title():
    valid, msg, _ = validate_sell_input(
        title="A",
        major_slug="ceit",
        year=1,
        semester="1",
        price=10000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=["photo_1"],
    )
    assert valid is False
    assert "စာအုပ်အမည်" in msg

def test_validate_sell_input_too_long_title():
    long_title = "A" * 121
    valid, msg, _ = validate_sell_input(
        title=long_title,
        major_slug="ceit",
        year=1,
        semester="1",
        price=10000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=["photo_1"],
    )
    assert valid is False
    assert "စာအုပ်အမည်" in msg

def test_validate_sell_input_invalid_major():
    valid, msg, _ = validate_sell_input(
        title="Valid Title",
        major_slug="invalid_major",
        year=1,
        semester="1",
        price=10000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=["photo_1"],
    )
    assert valid is False
    assert "မေဂျာ မမှန်ကန်ပါ" in msg

def test_validate_sell_input_year_out_of_bounds():
    for yr in [0, 7, 10]:
        valid, msg, _ = validate_sell_input(
            title="Valid Title",
            major_slug="ceit",
            year=yr,
            semester="1",
            price=10000,
            is_negotiable=False,
            condition="အသစ်နီးပါး",
            photo_file_ids=["photo_1"],
        )
        assert valid is False
        assert "ပညာသင်နှစ်" in msg

def test_validate_sell_input_year3_semesters():
    # Valid year 3 semester 1, 2, "1 & 2"
    for sem in ["1", "2", "1 & 2", 1, 2]:
        valid, _, clean = validate_sell_input(
            title="Signals and Systems",
            major_slug="ec",
            year=3,
            semester=sem,
            price=12000,
            is_negotiable=False,
            condition="အတော်အသင့်ကောင်း",
            photo_file_ids=["photo_1"],
        )
        assert valid is True
        assert clean["year"] == 3

    # Invalid year 3 semester 3 or 4
    for sem in ["3", "4", "3 & 4"]:
        valid, msg, _ = validate_sell_input(
            title="Signals and Systems",
            major_slug="ec",
            year=3,
            semester=sem,
            price=12000,
            is_negotiable=False,
            condition="အတော်အသင့်ကောင်း",
            photo_file_ids=["photo_1"],
        )
        assert valid is False
        assert "Semester မမှန်ကန်ပါ" in msg

def test_validate_sell_input_negative_and_zero_price():
    for p in [-1000, 0, None]:
        valid, msg, _ = validate_sell_input(
            title="Valid Title",
            major_slug="ep",
            year=1,
            semester="1",
            price=p,
            is_negotiable=False,
            condition="အသစ်နီးပါး",
            photo_file_ids=["photo_1"],
        )
        assert valid is False
        assert "ဈေးနှုန်း" in msg

def test_validate_sell_input_excessive_price():
    valid, msg, _ = validate_sell_input(
        title="Valid Title",
        major_slug="ep",
        year=1,
        semester="1",
        price=100_000_000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=["photo_1"],
    )
    assert valid is False
    assert "ဈေးနှုန်း ပမာဏများလွန်း" in msg

def test_validate_sell_input_too_many_photos():
    photos = ["p1", "p2", "p3", "p4", "p5"]
    valid, msg, _ = validate_sell_input(
        title="Valid Title",
        major_slug="civil",
        year=4,
        semester="1",
        price=15000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=photos,
    )
    assert valid is False
    assert "အများဆုံး ၄ ပုံ" in msg

def test_validate_sell_input_max_allowed_photos():
    photos = ["p1", "p2", "p3", "p4"]
    valid, _, clean = validate_sell_input(
        title="Valid Title",
        major_slug="civil",
        year=4,
        semester="1",
        price=15000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=photos,
    )
    assert valid is True
    assert len(clean["photo_file_ids"]) == 4
    assert clean["photo_file_id"] == "p1"


def test_validate_sell_input_canonical_used_with_details():
    valid, msg, clean = validate_sell_input(
        title="Compiler Design",
        major_slug="ceit",
        year=4,
        semester="1",
        price=20000,
        is_negotiable=False,
        condition="Used",
        photo_file_ids=["photo_cd_1"],
        condition_details="Slightly damaged cover, clean inside pages, no marks.",
    )
    assert valid is True
    assert clean["condition"] == "Used"
    assert clean["condition_details"] == "Slightly damaged cover, clean inside pages, no marks."


def test_validate_sell_input_canonical_used_without_details():
    valid, msg, clean = validate_sell_input(
        title="Control Systems",
        major_slug="ep",
        year=3,
        semester="2",
        price=18000,
        is_negotiable=False,
        condition="Used",
        photo_file_ids=["photo_cs_1"],
        condition_details=None,
    )
    assert valid is True
    assert clean["condition"] == "Used"
    assert clean["condition_details"] is None


def test_validate_sell_input_condition_details_too_long():
    long_desc = "A" * 501
    valid, msg, _ = validate_sell_input(
        title="Control Systems",
        major_slug="ep",
        year=3,
        semester="2",
        price=18000,
        is_negotiable=False,
        condition="Used",
        photo_file_ids=["photo_cs_1"],
        condition_details=long_desc,
    )
    assert valid is False
    assert "၅၀၀" in msg


def test_validate_sell_input_condition_details_whitespace_treated_as_none():
    valid, msg, clean = validate_sell_input(
        title="Control Systems",
        major_slug="ep",
        year=3,
        semester="2",
        price=18000,
        is_negotiable=False,
        condition="Used",
        photo_file_ids=["photo_cs_1"],
        condition_details="     ",
    )
    assert valid is True
    assert clean["condition_details"] is None

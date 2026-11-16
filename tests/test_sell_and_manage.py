# tests/test_sell_and_manage.py
"""Unit tests for Sell input validation and seller management rules."""
from datetime import datetime, timezone
import pytest
from app.services.sell_service import validate_sell_input
from app.api.routes.my_books_routes import EditListingRequest, MyBookDetailResponse

def test_validate_sell_input_valid_year1():
    valid, msg, clean = validate_sell_input(
        title="Physics Vol 1",
        major_slug="ceit",
        year=1,
        semester="1",
        price=15000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=["file_abc_123"],
    )
    assert valid is True
    assert clean["major"] == "CEIT"
    assert clean["price"] == 15000

def test_validate_sell_input_year2_mapping():
    # Year 2 only accepts semesters 3, 4, or '3 & 4'
    valid_y2, _, _ = validate_sell_input(
        title="Data Structures",
        major_slug="ceit",
        year=2,
        semester="3",
        price=20000,
        is_negotiable=False,
        condition="အတော်အသင့်ကောင်း",
        photo_file_ids=["file_xyz"],
    )
    assert valid_y2 is True

    # Invalid semester 1 for Year 2
    invalid_y2, msg, _ = validate_sell_input(
        title="Data Structures",
        major_slug="ceit",
        year=2,
        semester="1",
        price=20000,
        is_negotiable=False,
        condition="အတော်အသင့်ကောင်း",
        photo_file_ids=["file_xyz"],
    )
    assert invalid_y2 is False
    assert "Semester မမှန်ကန်ပါ" in msg

def test_validate_sell_input_negotiable():
    valid, _, clean = validate_sell_input(
        title="Calculus",
        major_slug="ep",
        year=1,
        semester="1 & 2",
        price=None,
        is_negotiable=True,
        condition="အသုံးပြုထားသည်",
        photo_file_ids=["photo1"],
    )
    assert valid is True
    assert clean["is_negotiable"] is True
    assert clean["price"] is None

def test_validate_sell_input_no_photos():
    valid, msg, _ = validate_sell_input(
        title="Calculus",
        major_slug="ep",
        year=1,
        semester="1",
        price=10000,
        is_negotiable=False,
        condition="အသစ်နီးပါး",
        photo_file_ids=[],
    )
    assert valid is False
    assert "ဓာတ်ပုံ" in msg

def test_edit_listing_request_schema():
    req = EditListingRequest(
        title="Modern Control Systems",
        major_slug="ep",
        year=3,
        semester="1",
        price=35000,
        is_negotiable=False,
        condition="Used",
        condition_details="Like new with minor pencil notes",
        photo_file_ids=["id1", "id2"],
    )
    assert req.title == "Modern Control Systems"
    assert req.major_slug == "ep"
    assert req.year == 3
    assert req.price == 35000
    assert len(req.photo_file_ids) == 2

def test_my_book_detail_response_includes_photos():
    data = {
        "_id": "60c72b2f9b1d8b2badbee5a0",
        "title": "Algorithms",
        "major": "CEIT",
        "major_slug": "ceit",
        "year": 2,
        "semester": "3",
        "price": 20000,
        "is_negotiable": False,
        "condition": "Used",
        "condition_details": "No tears",
        "seller_id": 12345,
        "status": "Available",
        "photo_file_ids": ["photo_1", "photo_2"],
        "created_at": datetime.now(timezone.utc),
    }
    resp = MyBookDetailResponse(**data)
    assert resp.photo_file_ids == ["photo_1", "photo_2"]
    assert resp.photo_count == 2
    assert resp.has_photos is True

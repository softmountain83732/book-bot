# tests/test_book_routes.py
"""Unit tests for book schemas, filters, and health check endpoints."""
from datetime import datetime, timezone
import pytest
from app.api.schemas.book_schemas import BookDetailResponse, BookListResponse, BooksListPage
from app.api.utils.semester import build_semester_filter
from app.api.routes.report_routes import SubmitReportRequest, REPORT_REASONS

def test_build_semester_filter_comprehensive():
    # Year 2 semester 3
    f3 = build_semester_filter(2, "3")
    assert f3 == {"semester": {"$in": [3, "3 & 4"]}}

    # Year 2 semester 4
    f4 = build_semester_filter(2, "4")
    assert f4 == {"semester": {"$in": [4, "3 & 4"]}}

    # Year 1 semester 1
    f1 = build_semester_filter(1, "1")
    assert f1 == {"semester": {"$in": [1, "1 & 2"]}}

    # Year 1 semester 2
    f2 = build_semester_filter(1, "2")
    assert f2 == {"semester": {"$in": [2, "1 & 2"]}}

    # All or None
    assert build_semester_filter(1, "all") == {}
    assert build_semester_filter(None, None) == {}
    assert build_semester_filter(None, "all") == {}

def test_book_list_response_schema():
    book_data = {
        "_id": "60c72b2f9b1d8b2badbee5a0",
        "title": "Introduction to Algorithms",
        "major": "CEIT",
        "major_slug": "ceit",
        "year": 2,
        "semester": "3",
        "price": 25000,
        "is_negotiable": False,
        "condition": "Used",
        "condition_details": "Highlighted chapters 1 to 3",
        "seller_id": 12345678,
        "seller_username": "john_doe",
        "status": "Available",
        "photo_file_ids": ["file_id_1", "file_id_2"],
        "photo_file_id": "file_id_1",
        "created_at": datetime.now(timezone.utc),
    }
    resp = BookListResponse(**book_data)
    assert resp.title == "Introduction to Algorithms"
    assert resp.id == "60c72b2f9b1d8b2badbee5a0"
    assert resp.condition == "Used"
    assert resp.condition_details == "Highlighted chapters 1 to 3"
    assert resp.is_favorite is False

def test_book_detail_response_backward_compatible():
    # Old document without condition_details
    book_data = {
        "_id": "60c72b2f9b1d8b2badbee5a1",
        "title": "Classic Physics",
        "major": "EP",
        "major_slug": "ep",
        "year": 1,
        "semester": "1",
        "price": 10000,
        "is_negotiable": False,
        "condition": "Used",
        "seller_id": 9999,
        "status": "Available",
        "photo_file_ids": ["file_id_x"],
        "created_at": datetime.now(timezone.utc),
    }
    resp = BookDetailResponse(**book_data)
    assert resp.condition == "Used"
    assert resp.condition_details is None

def test_books_list_page_schema():
    page = BooksListPage(
        items=[],
        total=0,
        page=1,
        page_size=20,
        has_next=False,
    )
    assert page.total == 0
    assert page.has_next is False
    assert len(page.items) == 0

def test_submit_report_request_schema():
    req = SubmitReportRequest(
        book_id="60c72b2f9b1d8b2badbee5a0",
        reason="spam",
        notes="Multiple duplicate listings",
    )
    assert req.reason == "spam"
    assert req.book_id == "60c72b2f9b1d8b2badbee5a0"
    assert "spam" in REPORT_REASONS

def test_health_check_endpoint():
    from fastapi.testclient import TestClient
    from app.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "hbtu-book-marketplace-api"

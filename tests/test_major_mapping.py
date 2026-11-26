# tests/test_major_mapping.py
"""Regression tests for Architecture and major slug normalization, mapping, and filtering."""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.schemas.book_schemas import BookDetailResponse, BookListResponse
from app.api.utils.major import (
    MAJOR_CANONICAL_SLUGS,
    MAJOR_DB_SLUGS,
    MAJOR_NAMES,
    build_major_filter,
    get_major_name,
    normalize_major_slug,
)
from app.handlers.browse import _listing_query as bot_listing_query
from app.services.sell_service import validate_sell_input


def test_normalize_major_slug():
    # Architecture aliases
    assert normalize_major_slug("arch") == "arch"
    assert normalize_major_slug("archi") == "arch"
    assert normalize_major_slug("Architecture") == "arch"
    assert normalize_major_slug("  ARCHI  ") == "arch"

    # Mechanical aliases
    assert normalize_major_slug("mech") == "mech"
    assert normalize_major_slug("me") == "mech"
    assert normalize_major_slug("Mechanical") == "mech"

    # Other majors
    assert normalize_major_slug("ceit") == "ceit"
    assert normalize_major_slug("ep") == "ep"
    assert normalize_major_slug("ec") == "ec"
    assert normalize_major_slug("mc") == "mc"
    assert normalize_major_slug("civil") == "civil"

    # Empty or None
    assert normalize_major_slug(None) is None
    assert normalize_major_slug("") is None


def test_get_major_name():
    assert get_major_name("arch") == "Architecture"
    assert get_major_name("archi") == "Architecture"
    assert get_major_name("mech") == "Mechanical"
    assert get_major_name("me") == "Mechanical"
    assert get_major_name("ceit") == "CEIT"
    assert get_major_name("civil") == "Civil"


def test_build_major_filter_empty():
    assert build_major_filter(None) == {}
    assert build_major_filter("") == {}
    assert build_major_filter("all") == {}


def test_build_major_filter_architecture():
    # Both "arch" and "archi" produce query matching all Architecture database variations
    filter_arch = build_major_filter("arch")
    assert "$or" in filter_arch
    conditions = filter_arch["$or"]
    assert {"major_slug": {"$in": ["arch", "archi"]}} in conditions
    assert {"major": "Architecture"} in conditions

    filter_archi = build_major_filter("archi")
    assert filter_archi == filter_arch

    filter_name = build_major_filter("Architecture")
    assert filter_name == filter_arch


def test_build_major_filter_mechanical():
    filter_mech = build_major_filter("mech")
    assert "$or" in filter_mech
    conditions = filter_mech["$or"]
    assert {"major_slug": {"$in": ["mech", "me"]}} in conditions
    assert {"major": "Mechanical"} in conditions

    filter_me = build_major_filter("me")
    assert filter_me == filter_mech


def test_build_major_filter_other_majors():
    for slug, expected_name in [
        ("ceit", "CEIT"),
        ("ep", "EP"),
        ("ec", "EC"),
        ("mc", "MC"),
        ("civil", "Civil"),
    ]:
        f = build_major_filter(slug)
        assert "$or" in f
        assert {"major_slug": {"$in": [slug]}} in f["$or"]
        assert {"major": expected_name} in f["$or"]


def test_book_list_response_normalizes_legacy_archi_slug():
    raw_doc = {
        "_id": "6af48f471cac20ef82da6e26",
        "title": "English/Mathematic/Chemistry/Physics/Workshop/Myanmar",
        "major": "Architecture",
        "major_slug": "archi",  # Legacy database slug
        "year": 1,
        "semester": "1 & 2",
        "price": None,
        "is_negotiable": True,
        "condition": "Used",
        "seller_id": 1878490032,
        "status": "Available",
        "created_at": datetime.now(timezone.utc),
    }
    resp = BookListResponse.model_validate(raw_doc)
    assert resp.major == "Architecture"
    assert resp.major_slug == "arch"  # Normalized to canonical Mini App slug


def test_book_detail_response_normalizes_legacy_me_slug():
    raw_doc = {
        "_id": "6afec5f262217307ea04c4f7",
        "title": "Thermodynamics",
        "major": "Mechanical",
        "major_slug": "me",  # Legacy database slug
        "year": 2,
        "semester": 3,
        "price": 20000,
        "is_negotiable": False,
        "condition": "Used",
        "seller_id": 9999,
        "status": "Available",
        "created_at": datetime.now(timezone.utc),
    }
    resp = BookDetailResponse.model_validate(raw_doc)
    assert resp.major == "Mechanical"
    assert resp.major_slug == "mech"


def test_validate_sell_input_accepts_arch_and_archi():
    # Accepts canonical "arch"
    ok, msg, clean = validate_sell_input(
        title="Architectural Drawing 1",
        major_slug="arch",
        year=1,
        semester=1,
        price=15000,
        is_negotiable=False,
        condition="Used",
        photo_file_ids=["file_1"],
    )
    assert ok is True
    assert clean["major"] == "Architecture"
    assert clean["major_slug"] == "arch"

    # Also accepts legacy "archi"
    ok2, msg2, clean2 = validate_sell_input(
        title="Architectural Drawing 1",
        major_slug="archi",
        year=1,
        semester=1,
        price=15000,
        is_negotiable=False,
        condition="Used",
        photo_file_ids=["file_1"],
    )
    assert ok2 is True
    assert clean2["major"] == "Architecture"
    assert clean2["major_slug"] == "arch"


def test_bot_listing_query_unchanged():
    # Verify Bot query logic remains fully compatible
    q = bot_listing_query("all", "archi")
    assert {"status": "Available"} in q["$and"]
    assert {"admin_hidden": {"$ne": True}} in q["$and"]
    assert {"$or": [{"major_slug": "archi"}, {"major": "Architecture"}]} in q["$and"]


def test_api_books_architecture_filter_returns_books():
    """Verify live API with Architecture filter returns existing database books."""
    with TestClient(app) as client:
        # Mini App queries with major_slug=arch
        r_arch = client.get("/api/v1/books?major_slug=arch")
        assert r_arch.status_code == 200
        data = r_arch.json()
        assert data["total"] == 4
        assert len(data["items"]) == 4
        for item in data["items"]:
            assert item["major"] == "Architecture"
            assert item["major_slug"] == "arch"

        # Also supports major_slug=archi
        r_archi = client.get("/api/v1/books?major_slug=archi")
        assert r_archi.status_code == 200
        assert r_archi.json()["total"] == 4


def test_api_books_other_major_filters():
    """Verify other major filters continue working."""
    with TestClient(app) as client:
        # CEIT
        r_ceit = client.get("/api/v1/books?major_slug=ceit")
        assert r_ceit.status_code == 200
        assert r_ceit.json()["total"] == 15  # 15 Available CEIT books in DB

        # Mechanical matches both mech and me
        r_mech = client.get("/api/v1/books?major_slug=mech")
        assert r_mech.status_code == 200
        assert r_mech.json()["total"] == 7  # All 7 Available Mechanical books

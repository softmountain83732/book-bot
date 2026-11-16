# tests/test_purchases_favorites.py
"""Unit tests for purchase and favorite endpoints logic."""
import pytest
from app.services.purchase_service import (
    build_buyer_purchase_message,
    get_price_display,
    telegram_contact_link,
)
from app.api.routes.purchase_routes import SellerContactResponse

def test_get_price_display():
    assert get_price_display({"is_negotiable": True, "price": 5000}) == "ဈေးညှိနှိုင်း"
    assert get_price_display({"is_negotiable": False, "price": 12000}) == "12,000 MMK"
    assert get_price_display({"is_negotiable": False, "price": None}) == "ဈေးနှုန်း မသတ်မှတ်ထားပါ"

def test_telegram_contact_link():
    assert telegram_contact_link(12345, "john_doe") == "@john_doe"
    assert "tg://user?id=12345" in telegram_contact_link(12345, None)

def test_build_buyer_purchase_message_with_seller_username():
    book = {
        "title": "Database Systems",
        "price": 18000,
        "is_negotiable": False,
        "major": "CEIT",
        "year": 2,
        "semester": 3,
        "seller_id": 987654,
        "seller_username": "book_seller",
    }
    msg = build_buyer_purchase_message(book)
    assert "Your purchase request has been received!" in msg
    assert "Book: Database Systems" in msg
    assert "Price: 18,000 MMK" in msg
    assert "Major: CEIT" in msg
    assert "Year: Year 2" in msg
    assert "Semester: Semester 3" in msg
    assert "👤 Seller: @book_seller" in msg
    assert "You can now contact the seller to discuss and arrange the transaction." in msg

def test_build_buyer_purchase_message_without_username_fallback():
    book = {
        "title": "Basic Electrical",
        "is_negotiable": True,
        "price": None,
        "major": "EP",
        "year": 1,
        "semester": "1 & 2",
        "seller_id": 555666,
    }
    msg = build_buyer_purchase_message(book, seller_username=None)
    assert "Book: Basic Electrical" in msg
    assert "Price: ဈေးညှိနှိုင်း" in msg
    assert "Major: EP" in msg
    assert "Year: Year 1" in msg
    assert "Semester: Both (1 &amp; 2)" in msg
    assert 'tg://user?id=555666' in msg

def test_seller_contact_response_schema():
    resp = SellerContactResponse(
        book_id="60c72b2f9b1d8b2badbee5a0",
        book_title="Physics 1",
        price=12000,
        is_negotiable=False,
        seller_id=112233,
        seller_username="@seller123",
        telegram_link="https://t.me/seller123",
        has_username=True,
    )
    assert resp.seller_username == "@seller123"
    assert resp.has_username is True
    assert resp.telegram_link == "https://t.me/seller123"

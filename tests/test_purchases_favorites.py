# tests/test_purchases_favorites.py
"""Unit tests for purchase and favorite endpoints logic."""
import pytest
from app.services.purchase_service import get_price_display, telegram_contact_link

def test_get_price_display():
    assert get_price_display({"is_negotiable": True, "price": 5000}) == "ဈေးညှိနှိုင်း"
    assert get_price_display({"is_negotiable": False, "price": 12000}) == "12,000 MMK"
    assert get_price_display({"is_negotiable": False, "price": None}) == "ဈေးနှုန်း မသတ်မှတ်ထားပါ"

def test_telegram_contact_link():
    assert telegram_contact_link(12345, "john_doe") == "@john_doe"
    assert "tg://user?id=12345" in telegram_contact_link(12345, None)

# tests/test_auth.py
"""Unit tests for Telegram initData validation and authentication flow."""
import hashlib
import hmac
import json
import time
import pytest
from app.api.auth import validate_telegram_init_data, create_access_token, decode_access_token
from app.config import settings

def generate_valid_init_data(user_id=12345678, username="teststudent", auth_date_offset=0):
    user_data = {
        "id": user_id,
        "first_name": "Ko",
        "last_name": "Test",
        "username": username,
        "language_code": "my"
    }
    user_str = json.dumps(user_data, separators=(",", ":"))
    auth_date = int(time.time()) + auth_date_offset
    
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohD9vYhO",
        "user": user_str
    }
    
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    
    params["hash"] = calc_hash
    # assemble URL query string
    from urllib.parse import urlencode
    return urlencode(params)

def test_valid_init_data_verification():
    raw = generate_valid_init_data()
    validated = validate_telegram_init_data(raw)
    assert validated.user.id == 12345678
    assert validated.user.username == "teststudent"
    assert validated.user.first_name == "Ko"

def test_tampered_init_data_fails():
    raw = generate_valid_init_data()
    # Tamper with the user ID in the query string
    tampered = raw.replace("12345678", "99999999")
    with pytest.raises(ValueError, match="Invalid hash signature"):
        validate_telegram_init_data(tampered)

def test_expired_init_data_fails():
    # 2 days old
    raw = generate_valid_init_data(auth_date_offset=-172800)
    with pytest.raises(ValueError, match="Expired initData"):
        validate_telegram_init_data(raw)

def test_jwt_token_roundtrip():
    token = create_access_token(user_id=88888, is_admin=True)
    payload = decode_access_token(token)
    assert payload["sub"] == "88888"
    assert payload["is_admin"] is True

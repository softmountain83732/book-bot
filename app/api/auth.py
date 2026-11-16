# app/api/auth.py
"""Telegram initData validation and JWT session generation."""
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict
from urllib.parse import parse_qsl, unquote

import jwt
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

# Fallback secret for local JWT signing (derived from bot token)
JWT_SECRET = hashlib.sha256(f"jwt-auth-{settings.bot_token}".encode()).hexdigest()
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 7 * 86400  # 7 days session


class TelegramUser(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = False
    allows_write_to_pm: bool | None = False


class ValidatedInitData(BaseModel):
    user: TelegramUser
    auth_date: int
    query_id: str | None = None
    hash: str


def validate_telegram_init_data(init_data_raw: str, max_age_seconds: int = 86400) -> ValidatedInitData:
    """Validate raw Telegram.WebApp.initData using official HMAC-SHA-256 procedure.
    
    Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    if not init_data_raw or not isinstance(init_data_raw, str):
        raise ValueError("Empty or invalid initData string")

    parsed_pairs = dict(parse_qsl(init_data_raw, keep_blank_values=True))
    received_hash = parsed_pairs.pop("hash", None)

    if not received_hash:
        raise ValueError("Missing 'hash' in initData")

    # Sort key-value pairs alphabetically and format as key=<value>
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_pairs.items()))

    # Secret key is HMAC-SHA256 of bot token with key "WebAppData"
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()

    # Calculate expected HMAC-SHA256 hash
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid hash signature: initData has been tampered with")

    # Check auth_date for expiration
    auth_date_str = parsed_pairs.get("auth_date")
    if not auth_date_str or not auth_date_str.isdigit():
        raise ValueError("Missing or invalid 'auth_date' in initData")

    auth_date = int(auth_date_str)
    now = int(time.time())

    # Protect against future date spoofing & expiry
    if auth_date > now + 300:
        raise ValueError("Invalid auth_date: timestamp in future")
    if now - auth_date > max_age_seconds:
        raise ValueError("Expired initData: authentication session timed out")

    # Parse user JSON
    user_raw = parsed_pairs.get("user")
    if not user_raw:
        raise ValueError("Missing 'user' field in initData")

    try:
        user_dict = json.loads(user_raw)
        user = TelegramUser(**user_dict)
    except Exception as exc:
        raise ValueError(f"Malformed user object in initData: {exc}")

    return ValidatedInitData(
        user=user,
        auth_date=auth_date,
        query_id=parsed_pairs.get("query_id"),
        hash=received_hash,
    )


def create_access_token(user_id: int, is_admin: bool) -> str:
    """Create a short/medium-lived JWT access token for authenticated session."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "is_admin": is_admin,
        "iat": now,
        "exp": now + JWT_EXPIRATION_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and verify JWT access token."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")

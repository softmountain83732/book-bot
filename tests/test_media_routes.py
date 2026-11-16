# tests/test_media_routes.py
"""Unit tests for media route proxy, photo caching, error handling, and photo schemas."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from telegram.error import BadRequest, NetworkError, TimedOut

from app.api.main import app
from app.api.routes.media_routes import (
    _file_url_cache,
    _resolve_file_url,
    _sanitize,
)
from app.api.schemas.book_schemas import BookDetailResponse, BookListResponse


def test_sanitize_bot_token():
    with patch("app.api.routes.media_routes.settings.bot_token", "SECRET_TOKEN_12345"):
        text = "Failed at https://api.telegram.org/botSECRET_TOKEN_12345/getFile"
        sanitized = _sanitize(text)
        assert "SECRET_TOKEN_12345" not in sanitized
        assert "[REDACTED_BOT_TOKEN]" in sanitized


def test_schema_compute_photo_fields_single_legacy():
    data = {
        "_id": str(ObjectId()),
        "title": "Legacy Book",
        "major": "CEIT",
        "major_slug": "ceit",
        "year": 1,
        "semester": 1,
        "price": 5000,
        "is_negotiable": False,
        "seller_id": 111,
        "status": "Available",
        "photo_file_id": "file_legacy_123",
        "created_at": "2026-11-16T12:00:00Z",
    }
    resp = BookListResponse.model_validate(data)
    assert resp.photo_count == 1
    assert resp.has_photos is True
    # Ensure raw file IDs are excluded from serialized output
    dumped = resp.model_dump()
    assert "photo_file_ids" not in dumped
    assert "photo_file_id" not in dumped


def test_schema_compute_photo_fields_multiple_photos():
    data = {
        "_id": str(ObjectId()),
        "title": "Multi Photo Book",
        "major": "EP",
        "major_slug": "ep",
        "year": 2,
        "semester": "3",
        "price": 12000,
        "is_negotiable": False,
        "seller_id": 222,
        "status": "Available",
        "photo_file_ids": ["file_a", "file_b", "file_c"],
        "created_at": "2026-11-16T12:00:00Z",
    }
    resp = BookDetailResponse.model_validate(data)
    assert resp.photo_count == 3
    assert resp.has_photos is True
    dumped = resp.model_dump()
    assert "photo_file_ids" not in dumped


def test_schema_compute_photo_fields_no_photos():
    data = {
        "_id": str(ObjectId()),
        "title": "Text Only Book",
        "major": "EC",
        "major_slug": "ec",
        "year": 3,
        "semester": 1,
        "price": 8000,
        "is_negotiable": True,
        "seller_id": 333,
        "status": "Available",
        "photo_file_ids": [],
        "created_at": "2026-11-16T12:00:00Z",
    }
    resp = BookListResponse.model_validate(data)
    assert resp.photo_count == 0
    assert resp.has_photos is False


def test_resolve_file_url_cache_hit():
    async def _test():
        _file_url_cache.clear()
        now = time.time()
        _file_url_cache["test_fid"] = ("https://api.telegram.org/file/botXXX/test.jpg", now + 1000)

        bot = MagicMock()
        bot.get_file = AsyncMock()

        url = await _resolve_file_url(bot, "test_fid")
        assert url == "https://api.telegram.org/file/botXXX/test.jpg"
        bot.get_file.assert_not_called()

    asyncio.run(_test())


def test_resolve_file_url_expired_cache():
    async def _test():
        _file_url_cache.clear()
        now = time.time()
        # Cache expired 10 seconds ago
        _file_url_cache["test_fid_exp"] = ("https://api.telegram.org/old.jpg", now - 10)

        bot = MagicMock()
        mock_file = MagicMock()
        mock_file.file_path = "https://api.telegram.org/new.jpg"
        bot.get_file = AsyncMock(return_value=mock_file)

        url = await _resolve_file_url(bot, "test_fid_exp")
        assert url == "https://api.telegram.org/new.jpg"
        bot.get_file.assert_called_once_with("test_fid_exp")

    asyncio.run(_test())


def test_resolve_file_url_bad_request_raises_404():
    async def _test():
        _file_url_cache.clear()
        bot = MagicMock()
        bot.get_file = AsyncMock(side_effect=BadRequest("Wrong file identifier/HTTP URL specified"))

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_file_url(bot, "invalid_fid_999")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()
        # Ensure failed resolution was not cached
        assert "invalid_fid_999" not in _file_url_cache

    asyncio.run(_test())


def test_resolve_file_url_timeout_raises_503():
    async def _test():
        _file_url_cache.clear()
        bot = MagicMock()
        bot.get_file = AsyncMock(side_effect=TimedOut("Timed out"))

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_file_url(bot, "timeout_fid")

        # Timeouts must return 503, NOT 404
        assert exc_info.value.status_code == 503
        assert "Retry-After" in exc_info.value.headers
        assert "timeout_fid" not in _file_url_cache

    asyncio.run(_test())


def test_get_book_photo_invalid_object_id():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/media/books/not-a-valid-id/photos/0")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Book not found"


def test_get_book_photo_etag_304():
    book_id = str(ObjectId())
    file_id = "test_file_etag_123"
    etag = f'"{file_id}_0"'

    mock_db = MagicMock()
    mock_db.books.find_one = AsyncMock(return_value={
        "_id": ObjectId(book_id),
        "photo_file_ids": [file_id],
        "admin_hidden": False,
        "status": "Available",
    })

    with patch("app.api.routes.media_routes.get_database", return_value=mock_db):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            f"/api/v1/media/books/{book_id}/photos/0",
            headers={"if-none-match": etag},
        )
        assert resp.status_code == 304
        assert resp.headers.get("etag") == etag


def test_get_book_photo_index_out_of_range():
    book_id = str(ObjectId())
    mock_db = MagicMock()
    mock_db.books.find_one = AsyncMock(return_value={
        "_id": ObjectId(book_id),
        "photo_file_ids": ["file_single"],
        "admin_hidden": False,
        "status": "Available",
    })

    with patch("app.api.routes.media_routes.get_database", return_value=mock_db):
        client = TestClient(app, raise_server_exceptions=False)
        # Only 1 photo exists (index 0), requesting index 1 should 404
        resp = client.get(f"/api/v1/media/books/{book_id}/photos/1")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Photo index out of range"


def test_get_book_photo_no_photos_404():
    book_id = str(ObjectId())
    mock_db = MagicMock()
    mock_db.books.find_one = AsyncMock(return_value={
        "_id": ObjectId(book_id),
        "photo_file_ids": [],
        "admin_hidden": False,
        "status": "Available",
    })

    with patch("app.api.routes.media_routes.get_database", return_value=mock_db):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/media/books/{book_id}/photos/0")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No photos available for this book"

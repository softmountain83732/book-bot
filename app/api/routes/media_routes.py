# app/api/routes/media_routes.py
"""Secure Telegram photo proxy endpoint with caching, retries, and error handling."""
import asyncio
import logging
import time
from typing import Optional

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.request import HTTPXRequest

from app.config import settings
from app.database.mongo import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/media", tags=["Media"])

# Cache resolved Telegram file URLs in memory: file_id -> (url, expiration_timestamp)
# Telegram guarantees direct file download links are valid for at least 1 hour.
# We set TTL to 50 minutes (3000 seconds) so URLs are refreshed before expiring.
_file_url_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL_SECONDS = 3000

# Shared Telegram Bot and HTTP client singletons to avoid socket exhaustion
_shared_bot: Optional[Bot] = None
_media_http_client: Optional[httpx.AsyncClient] = None


def _sanitize(text: str) -> str:
    """Mask bot token in error logs to prevent credential leakage."""
    if settings.bot_token and settings.bot_token in text:
        return text.replace(settings.bot_token, "[REDACTED_BOT_TOKEN]")
    return text


def get_telegram_bot() -> Bot:
    """Get or initialize the shared Telegram Bot instance with robust connection pool."""
    global _shared_bot
    if _shared_bot is None:
        request = HTTPXRequest(
            connection_pool_size=32,
            connect_timeout=10.0,
            read_timeout=20.0,
            write_timeout=20.0,
        )
        _shared_bot = Bot(token=settings.bot_token, request=request)
    return _shared_bot


def get_media_http_client() -> httpx.AsyncClient:
    """Get or initialize the shared HTTPX async client for Telegram CDN downloads."""
    global _media_http_client
    if _media_http_client is None or _media_http_client.is_closed:
        _media_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=25.0, write=10.0, pool=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            follow_redirects=True,
        )
    return _media_http_client


async def close_media_resources():
    """Cleanly release media HTTP resources on application shutdown."""
    global _media_http_client, _shared_bot
    if _media_http_client and not _media_http_client.is_closed:
        await _media_http_client.aclose()
        _media_http_client = None
    if _shared_bot:
        try:
            await _shared_bot.shutdown()
        except Exception:
            pass
        _shared_bot = None


async def _resolve_file_url(bot: Bot, file_id: str, force_refresh: bool = False) -> str:
    """Resolve a Telegram file_id to a full CDN download URL with caching and retries.
    
    - Validates cache expiration.
    - Retries transient timeouts and network errors with exponential backoff.
    - Immediately raises 404 on BadRequest (invalid or genuinely missing file).
    - Never caches failed resolutions.
    """
    now = time.time()
    if not force_refresh and file_id in _file_url_cache:
        cached_url, expire_at = _file_url_cache[file_id]
        if now < expire_at:
            return cached_url
        _file_url_cache.pop(file_id, None)

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            tg_file = await bot.get_file(file_id)
            if not tg_file or not tg_file.file_path:
                logger.warning("Telegram returned empty file_path for file_id %s", file_id)
                raise HTTPException(status_code=404, detail="Photo file path not found")

            file_url = tg_file.file_path
            # In case the file_path is relative, format full Telegram download URL
            if not file_url.startswith(("http://", "https://")):
                file_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file_url.lstrip('/')}"

            # Cache the successful URL resolution
            _file_url_cache[file_id] = (file_url, now + CACHE_TTL_SECONDS)
            return file_url

        except BadRequest as err:
            # Permanent failure: invalid file_id or file deleted on Telegram servers
            logger.warning("Telegram BadRequest resolving file %s: %s", file_id, _sanitize(str(err)))
            _file_url_cache.pop(file_id, None)
            raise HTTPException(status_code=404, detail="Photo not found on Telegram")

        except (TimedOut, NetworkError) as err:
            if attempt < max_retries:
                backoff = 0.5 * (2 ** attempt)
                logger.info(
                    "Telegram get_file network glitch (%s), retrying in %.1fs (attempt %d/%d)",
                    _sanitize(str(err)),
                    backoff,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(backoff)
                continue

            logger.warning(
                "Telegram get_file failed after %d attempts for file_id %s: %s",
                max_retries + 1,
                file_id,
                _sanitize(str(err)),
            )
            # Transient timeout - do NOT disguise as 404!
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Telegram media service temporarily timed out. Please retry.",
                headers={"Retry-After": "3"},
            )

        except RetryAfter as err:
            sleep_time = min(getattr(err, "retry_after", 2.0), 3.0)
            if attempt < max_retries:
                logger.info("Telegram rate limit reached, backing off for %.1fs", sleep_time)
                await asyncio.sleep(sleep_time)
                continue
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Telegram photo service rate limited",
                headers={"Retry-After": str(int(getattr(err, "retry_after", 3)))},
            )

        except TelegramError as err:
            logger.error("Unexpected Telegram error resolving file %s: %s", file_id, _sanitize(str(err)))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to retrieve photo information from Telegram",
            )


@router.get("/books/{book_id}/photos/{photo_index}")
async def get_book_photo(
    book_id: str,
    photo_index: int,
    request: Request,
):
    """Stream a book photo securely via Telegram Bot API proxy.

    - BOT_TOKEN is never exposed to the client.
    - File access is strictly scoped to the requested book and photo index.
    - Responses include ETag and Cache-Control headers for browser caching.
    - Transient Telegram CDN / API timeouts return 503 with Retry-After.
    - Genuinely missing or invalid files return 404.
    """
    try:
        oid = ObjectId(book_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=404, detail="Book not found")

    db = get_database()
    try:
        doc = await db.books.find_one(
            {"_id": oid},
            {"photo_file_ids": 1, "photo_file_id": 1, "admin_hidden": 1, "status": 1},
        )
    except Exception:
        logger.exception("DB error fetching book %s for media proxy", book_id)
        raise HTTPException(status_code=503, detail="Database error")

    if doc is None or doc.get("admin_hidden"):
        raise HTTPException(status_code=404, detail="Book not found")

    # Collect photo file IDs (supporting both multi-photo list and legacy single-photo field)
    file_ids: list[str] = doc.get("photo_file_ids") or []
    if not file_ids and doc.get("photo_file_id"):
        file_ids = [doc["photo_file_id"]]

    if not file_ids:
        raise HTTPException(status_code=404, detail="No photos available for this book")

    if photo_index < 0 or photo_index >= len(file_ids):
        raise HTTPException(status_code=404, detail="Photo index out of range")

    file_id = file_ids[photo_index]
    etag = f'"{file_id}_{photo_index}"'

    # Respond with 304 Not Modified if browser ETag matches
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=86400, stale-while-revalidate=3600",
            },
        )

    bot = get_telegram_bot()
    file_url = await _resolve_file_url(bot, file_id)

    # Download image bytes from Telegram CDN
    client = get_media_http_client()
    try:
        tg_response = await client.get(file_url)

        # If Telegram CDN returns 403 or 404, the link may have expired early; force refresh once
        if tg_response.status_code in (403, 404):
            logger.info("Telegram CDN download returned %d for %s; refreshing link...", tg_response.status_code, file_id)
            _file_url_cache.pop(file_id, None)
            file_url = await _resolve_file_url(bot, file_id, force_refresh=True)
            tg_response = await client.get(file_url)

        tg_response.raise_for_status()

    except httpx.HTTPStatusError as err:
        status_code = err.response.status_code
        logger.warning("Telegram CDN HTTP status error %d for file_id %s", status_code, file_id)
        if status_code == 404:
            raise HTTPException(status_code=404, detail="Photo file not found on Telegram CDN")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo temporarily unavailable from CDN",
            headers={"Retry-After": "3"},
        )

    except (httpx.TimeoutException, httpx.NetworkError) as err:
        logger.warning("Telegram CDN download timeout for file_id %s: %s", file_id, _sanitize(str(err)))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo download timed out. Please retry.",
            headers={"Retry-After": "3"},
        )

    except httpx.HTTPError as err:
        logger.warning("Telegram CDN download failed for file_id %s: %s", file_id, _sanitize(str(err)))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo temporarily unavailable",
            headers={"Retry-After": "3"},
        )

    # Detect appropriate Content-Type header
    raw_content = tg_response.content
    content_type = tg_response.headers.get("content-type")
    if not content_type or content_type == "application/octet-stream":
        if raw_content.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
        elif raw_content.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = "image/png"
        elif raw_content.startswith(b"RIFF") and len(raw_content) >= 12 and raw_content[8:12] == b"WEBP":
            content_type = "image/webp"
        else:
            content_type = "image/jpeg"

    headers = {
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=3600",
        "ETag": etag,
        "Content-Type": content_type,
    }

    return Response(
        content=raw_content,
        status_code=200,
        headers=headers,
        media_type=content_type,
    )

# app/api/routes/book_routes.py
"""Book browsing and search API endpoints."""
import logging
import re
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import AuthContext, get_optional_user, get_db
from app.api.schemas.book_schemas import BookDetailResponse, BookListResponse, BooksListPage
from app.api.utils.major import build_major_filter
from app.api.utils.semester import build_semester_filter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/books", tags=["Books"])

# Fields projected from MongoDB - excludes internal Telegram file IDs from listing
_LIST_PROJECTION = {
    "_id": 1,
    "title": 1,
    "major": 1,
    "major_slug": 1,
    "year": 1,
    "semester": 1,
    "price": 1,
    "is_negotiable": 1,
    "condition": 1,
    "condition_details": 1,
    "seller_id": 1,
    "status": 1,
    "photo_file_ids": 1,
    "photo_file_id": 1,
    "admin_hidden": 1,
    "created_at": 1,
}

_DETAIL_PROJECTION = {
    **_LIST_PROJECTION,
    "current_buyer_id": 1,
    "channel_message_id": 1,
    "updated_at": 1,
}


@router.get("", response_model=BooksListPage)
async def list_books(
    year: Optional[int] = Query(None, ge=1, le=6),
    major_slug: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncDatabase = Depends(get_db),
):
    """List publicly available books with optional filters and search."""
    query: dict = {
        "status": "Available",
        "admin_hidden": {"$ne": True},
    }

    if year is not None:
        query["year"] = year

    major_filter = build_major_filter(major_slug)
    if major_filter:
        query.update(major_filter)

    sem_filter = build_semester_filter(year, semester)
    if sem_filter:
        query.update(sem_filter)

    if search and search.strip():
        escaped = re.escape(search.strip())
        query["title"] = {"$regex": escaped, "$options": "i"}

    skip = (page - 1) * page_size

    try:
        total = await db.books.count_documents(query)
        cursor = (
            db.books.find(query, _LIST_PROJECTION)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        books = []
        async for doc in cursor:
            books.append(BookListResponse.model_validate(doc))
    except Exception:
        logger.exception("Failed to query books collection")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database query failed",
        )

    return BooksListPage(
        items=books,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(skip + page_size) < total,
    )


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(
    book_id: str,
    auth: Optional[AuthContext] = Depends(get_optional_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Get full book details by ID."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        doc = await db.books.find_one({"_id": oid}, _DETAIL_PROJECTION)
    except Exception:
        logger.exception("Failed to fetch book %s", book_id)
        raise HTTPException(status_code=503, detail="Database error")

    if doc is None:
        raise HTTPException(status_code=404, detail="Book not found")

    # Hide admin-hidden books from non-admins
    is_admin = auth.is_admin if auth else False
    if doc.get("admin_hidden") and not is_admin:
        raise HTTPException(status_code=404, detail="Book not found")

    # Check favorite status
    is_fav = False
    if auth:
        fav = await db.favorites.find_one({"user_id": auth.user_id, "book_id": oid})
        is_fav = fav is not None

    doc["is_favorite"] = is_fav
    return BookDetailResponse.model_validate(doc)

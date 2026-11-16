# app/api/routes/favorite_routes.py
"""Favorites management API endpoints."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.api.deps import AuthContext, get_current_user, get_db
from app.api.schemas.book_schemas import BookListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/favorites", tags=["Favorites"])


class FavoriteToggleResponse(BaseModel):
    book_id: str
    is_favorite: bool
    message: str


class FavoritesListPage(BaseModel):
    items: List[BookListResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


@router.get("", response_model=FavoritesListPage)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieve saved favorites for the authenticated user with book details."""
    skip = (page - 1) * page_size
    user_id = auth.user_id

    total = await db.favorites.count_documents({"user_id": user_id})

    # Join with books collection
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"created_at": -1}},
        {"$skip": skip},
        {"$limit": page_size},
        {
            "$lookup": {
                "from": "books",
                "localField": "book_id",
                "foreignField": "_id",
                "as": "book",
            }
        },
        {"$unwind": "$book"},
        {"$replaceRoot": {"newRoot": "$book"}},
    ]

    cursor = db.favorites.aggregate(pipeline)
    items = []
    async for doc in cursor:
        doc["is_favorite"] = True
        items.append(BookListResponse.model_validate(doc))

    return FavoritesListPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(skip + page_size) < total,
    )


@router.post("/{book_id}", response_model=FavoriteToggleResponse)
async def add_favorite(
    book_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Add a book to user's favorites."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    # Check book exists and not owned by user
    book = await db.books.find_one({"_id": oid, "admin_hidden": {"$ne": True}})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("seller_id") == auth.user_id:
        raise HTTPException(status_code=400, detail="Cannot favorite your own listing")

    now = datetime.now(timezone.utc)
    try:
        await db.favorites.update_one(
            {"user_id": auth.user_id, "book_id": oid},
            {"$setOnInsert": {"user_id": auth.user_id, "book_id": oid, "created_at": now}},
            upsert=True,
        )
    except DuplicateKeyError:
        pass

    return FavoriteToggleResponse(
        book_id=book_id,
        is_favorite=True,
        message="သိမ်းထားသော စာရင်းထဲသို့ ထည့်ပြီးပါပြီ။",
    )


@router.delete("/{book_id}", response_model=FavoriteToggleResponse)
async def remove_favorite(
    book_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Remove a book from user's favorites."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    await db.favorites.delete_one({"user_id": auth.user_id, "book_id": oid})

    return FavoriteToggleResponse(
        book_id=book_id,
        is_favorite=False,
        message="သိမ်းထားသော စာရင်းမှ ဖယ်ရှားပြီးပါပြီ။",
    )

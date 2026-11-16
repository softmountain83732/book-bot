# app/api/routes/my_books_routes.py
"""Seller management API endpoints: My Books, metrics, edit, delist, relist, and permanent delete."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from telegram import Bot

from app.api.deps import AuthContext, get_current_user, get_db
from app.api.schemas.book_schemas import BookDetailResponse, BookListResponse
from app.config import settings
from app.services.channel_service import update_book_channel
from app.services.seller_manage_service import (
    seller_change_status,
    seller_permanently_delete_listing,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/my-books", tags=["My Books"])


class SellerDashboardMetrics(BaseModel):
    active_count: int
    pending_count: int
    sold_count: int
    delisted_count: int
    total_count: int


class MyBooksListPage(BaseModel):
    items: List[BookListResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class StatusActionRequest(BaseModel):
    action: str  # "delist", "relist", or "delete"


class EditListingRequest(BaseModel):
    title: Optional[str] = None
    price: Optional[float] = None
    is_negotiable: Optional[bool] = None
    condition: Optional[str] = None
    condition_details: Optional[str] = None


@router.get("/metrics", response_model=SellerDashboardMetrics)
async def get_seller_metrics(
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieve seller's listings statistics."""
    user_id = auth.user_id
    pipeline = [
        {"$match": {"seller_id": user_id, "status": {"$ne": "Deleted"}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    cursor = db.books.aggregate(pipeline)
    counts: Dict[str, int] = {}
    async for row in cursor:
        counts[row["_id"]] = row["count"]

    active = counts.get("Available", 0)
    pending = counts.get("Pending", 0)
    sold = counts.get("Sold", 0)
    delisted = counts.get("Delisted", 0)
    total = sum(counts.values())

    return SellerDashboardMetrics(
        active_count=active,
        pending_count=pending,
        sold_count=sold,
        delisted_count=delisted,
        total_count=total,
    )


@router.get("", response_model=MyBooksListPage)
async def list_my_books(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """List seller's owned listings with optional status tab filtering."""
    skip = (page - 1) * page_size
    query: Dict[str, Any] = {"seller_id": auth.user_id}

    if status_filter and status_filter != "all":
        query["status"] = status_filter
    else:
        query["status"] = {"$ne": "Deleted"}

    total = await db.books.count_documents(query)
    cursor = db.books.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    items = []
    async for doc in cursor:
        items.append(BookListResponse.model_validate(doc))

    return MyBooksListPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(skip + page_size) < total,
    )


@router.put("/{book_id}")
async def edit_my_book(
    book_id: str,
    body: EditListingRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Edit listing details (title, price, condition, negotiable)."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = await db.books.find_one({"_id": oid, "seller_id": auth.user_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("status") != "Available" or book.get("admin_hidden"):
        raise HTTPException(status_code=400, detail="Only Available listings can be edited")

    update_fields: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if body.title is not None and len(body.title.strip()) >= 2:
        update_fields["title"] = body.title.strip()
    if body.is_negotiable is not None:
        update_fields["is_negotiable"] = body.is_negotiable
        if body.is_negotiable:
            update_fields["price"] = None
        elif body.price is not None:
            update_fields["price"] = body.price
    elif body.price is not None:
        update_fields["price"] = body.price

    if body.condition is not None and len(body.condition.strip()) >= 2:
        update_fields["condition"] = body.condition.strip()

    if body.condition_details is not None:
        det = body.condition_details.strip()
        update_fields["condition_details"] = det if det else None

    await db.books.update_one({"_id": oid}, {"$set": update_fields})

    # Synchronize updated details to Channel
    updated_doc = await db.books.find_one({"_id": oid})
    if updated_doc and updated_doc.get("channel_message_id"):
        bot = Bot(token=settings.bot_token)
        try:
            await update_book_channel(bot, updated_doc, status="Available")
        except Exception:
            logger.exception("Failed to update channel caption on edit for %s", book_id)

    return {"status": "updated", "message": "စာအုပ်အချက်အလက်ကို ပြင်ဆင်ပြီးပါပြီ။"}


@router.post("/{book_id}/action")
async def seller_action_endpoint(
    book_id: str,
    body: StatusActionRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Perform delist, relist, or permanent channel post delete."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    bot = Bot(token=settings.bot_token)
    action = body.action.lower()

    if action == "delist":
        success, msg = await seller_change_status(db, bot, auth.user_id, oid, "Delisted")
    elif action == "relist":
        success, msg = await seller_change_status(db, bot, auth.user_id, oid, "Available")
    elif action == "delete":
        success, msg = await seller_permanently_delete_listing(db, bot, auth.user_id, oid)
    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {"success": True, "message": msg}

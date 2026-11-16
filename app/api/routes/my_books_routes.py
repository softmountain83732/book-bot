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
from app.services.sell_service import VALID_MAJORS
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
    major_slug: Optional[str] = None
    year: Optional[int] = None
    semester: Optional[Any] = None
    price: Optional[float] = None
    is_negotiable: Optional[bool] = None
    condition: Optional[str] = None
    condition_details: Optional[str] = None
    photo_file_ids: Optional[List[str]] = None


class MyBookDetailResponse(BookDetailResponse):
    photo_file_ids: List[str] = []


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


@router.get("/{book_id}", response_model=MyBookDetailResponse)
async def get_my_book_detail(
    book_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieve full listing details including photo_file_ids for seller editing."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = await db.books.find_one({"_id": oid, "seller_id": auth.user_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Normalize photo_file_ids
    if "photo_file_ids" not in book or not book["photo_file_ids"]:
        if book.get("photo_file_id"):
            book["photo_file_ids"] = [book["photo_file_id"]]
        else:
            book["photo_file_ids"] = []

    return MyBookDetailResponse.model_validate(book)


@router.put("/{book_id}")
async def edit_my_book(
    book_id: str,
    body: EditListingRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Edit listing details (title, major, year, semester, price, negotiable, condition, photos)."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = await db.books.find_one({"_id": oid, "seller_id": auth.user_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("status") not in ("Available", "Delisted") or book.get("admin_hidden"):
        raise HTTPException(status_code=400, detail="Only Available or Delisted listings can be edited")

    update_fields: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}

    # Title validation
    if body.title is not None:
        clean_title = body.title.strip()
        if len(clean_title) < 2 or len(clean_title) > 120:
            raise HTTPException(status_code=400, detail="စာအုပ်အမည်သည် အနည်းဆုံး ၂ လုံးမှ ၁၂၀ လုံးအတွင်း ဖြစ်ရပါမည်။")
        update_fields["title"] = clean_title

    # Major validation
    if body.major_slug is not None:
        clean_slug = body.major_slug.lower().strip()
        if clean_slug not in VALID_MAJORS:
            raise HTTPException(status_code=400, detail="မေဂျာ မမှန်ကန်ပါ။")
        update_fields["major_slug"] = clean_slug
        update_fields["major"] = VALID_MAJORS[clean_slug]

    # Year & Semester validation
    new_year = body.year if body.year is not None else book.get("year", 1)
    new_semester = body.semester if body.semester is not None else book.get("semester", 1)
    if body.year is not None or body.semester is not None:
        if new_year not in [1, 2, 3, 4, 5, 6]:
            raise HTTPException(status_code=400, detail="ပညာသင်နှစ်သည် Year 1 မှ Year 6 အတွင်း ဖြစ်ရပါမည်။")

        str_sem = str(new_semester).strip()
        if new_year == 2:
            valid_semesters = {"3", "4", "3 & 4", 3, 4}
        else:
            valid_semesters = {"1", "2", "1 & 2", 1, 2}

        if new_semester not in valid_semesters and str_sem not in valid_semesters:
            raise HTTPException(status_code=400, detail=f"Year {new_year} အတွက် Semester မမှန်ကန်ပါ။")

        update_fields["year"] = new_year
        update_fields["semester"] = new_semester if isinstance(new_semester, (int, str)) else str_sem

    # Price & Negotiable validation
    new_is_negotiable = body.is_negotiable if body.is_negotiable is not None else book.get("is_negotiable", False)
    update_fields["is_negotiable"] = bool(new_is_negotiable)
    if new_is_negotiable:
        update_fields["price"] = None
    else:
        new_price = body.price if body.price is not None else book.get("price")
        if new_price is None or float(new_price) <= 0:
            raise HTTPException(status_code=400, detail="ဈေးနှုန်း မသတ်မှတ်ရသေးပါ (သို့မဟုတ်) ဈေးညှိနှိုင်းဟု ရွေးချယ်ပေးပါ။")
        if float(new_price) > 10_000_000:
            raise HTTPException(status_code=400, detail="ဈေးနှုန်း ပမာဏများလွန်းနေပါသည်။")
        update_fields["price"] = float(new_price)

    # Condition
    if body.condition is not None:
        clean_cond = body.condition.strip()
        if len(clean_cond) < 2:
            clean_cond = "Used"
        update_fields["condition"] = clean_cond

    # Condition details
    if body.condition_details is not None:
        det = body.condition_details.strip()
        if len(det) > 500:
            raise HTTPException(status_code=400, detail="စာအုပ်အခြေအနေ အသေးစိတ်သည် စာလုံးရေ ၅၀၀ ထက် မကျော်ရပါ။")
        update_fields["condition_details"] = det if det else None

    # Photos
    photos_updated = False
    if body.photo_file_ids is not None:
        if len(body.photo_file_ids) == 0:
            raise HTTPException(status_code=400, detail="အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ တင်ပေးရန် လိုအပ်ပါသည်။")
        if len(body.photo_file_ids) > 4:
            raise HTTPException(status_code=400, detail="ဓာတ်ပုံ အများဆုံး ၄ ပုံသာ တင်နိုင်ပါသည်။")
        update_fields["photo_file_ids"] = body.photo_file_ids[:4]
        update_fields["photo_file_id"] = body.photo_file_ids[0]
        update_fields["photo_count"] = len(body.photo_file_ids[:4])
        update_fields["has_photos"] = True
        photos_updated = True

    await db.books.update_one({"_id": oid}, {"$set": update_fields})

    # Synchronize updated details to Channel
    updated_doc = await db.books.find_one({"_id": oid})
    if updated_doc and updated_doc.get("channel_message_id"):
        bot = Bot(token=settings.bot_token)
        try:
            await update_book_channel(
                bot,
                updated_doc,
                status=updated_doc.get("status", "Available"),
                update_photo=photos_updated,
            )
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

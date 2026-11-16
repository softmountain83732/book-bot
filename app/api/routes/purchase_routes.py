# app/api/routes/purchase_routes.py
"""Purchase and Buyer workflow API endpoints."""
import logging
from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from telegram import Bot

from app.api.deps import AuthContext, get_current_user, get_db
from app.config import settings
from app.services.purchase_service import buy_book_claim, cancel_purchase_claim

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/purchases", tags=["Purchases"])


class BuyRequest(BaseModel):
    book_id: str


class BuyResponse(BaseModel):
    success: bool
    message: str
    request_id: Optional[str] = None


class CancelPurchaseRequest(BaseModel):
    request_id: str


class CancelPurchaseResponse(BaseModel):
    success: bool
    message: str


class PurchaseRequestItem(BaseModel):
    id: str
    book_id: str
    book_title: str
    seller_id: int
    seller_username: Optional[str] = None
    price: Optional[float] = None
    is_negotiable: bool = False
    status: str
    created_at: datetime
    updated_at: datetime


class PurchaseHistoryPage(BaseModel):
    items: List[PurchaseRequestItem]
    total: int
    page: int
    page_size: int
    has_next: bool


@router.post("/buy", response_model=BuyResponse)
async def buy_book(
    body: BuyRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Initiate an atomic book purchase claim."""
    try:
        book_oid = ObjectId(body.book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    bot = Bot(token=settings.bot_token)
    user_info = auth.user_data
    username = user_info.get("username") if user_info else None

    success, message, request_id = await buy_book_claim(
        db=db,
        bot=bot,
        buyer_id=auth.user_id,
        buyer_username=username,
        book_id=book_oid,
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return BuyResponse(
        success=True,
        message=message,
        request_id=str(request_id) if request_id else None,
    )


@router.post("/cancel", response_model=CancelPurchaseResponse)
async def cancel_purchase(
    body: CancelPurchaseRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Execute buyer two-step cancellation for a pending request."""
    try:
        req_oid = ObjectId(body.request_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid request ID")

    bot = Bot(token=settings.bot_token)
    success, message = await cancel_purchase_claim(
        db=db,
        bot=bot,
        buyer_id=auth.user_id,
        request_id=req_oid,
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return CancelPurchaseResponse(
        success=True,
        message=message,
    )


@router.get("/history", response_model=PurchaseHistoryPage)
async def purchase_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Fetch user's purchase requests history."""
    skip = (page - 1) * page_size
    buyer_id = auth.user_id

    total = await db.purchase_requests.count_documents({"buyer_id": buyer_id})

    pipeline = [
        {"$match": {"buyer_id": buyer_id}},
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
        {"$unwind": {"path": "$book", "preserveNullAndEmptyArrays": True}},
    ]

    cursor = db.purchase_requests.aggregate(pipeline)
    items = []
    async for doc in cursor:
        book_info = doc.get("book") or {}
        items.append(
            PurchaseRequestItem(
                id=str(doc["_id"]),
                book_id=str(doc["book_id"]),
                book_title=book_info.get("title", "Untitled listing"),
                seller_id=doc["seller_id"],
                seller_username=book_info.get("seller_username"),
                price=book_info.get("price"),
                is_negotiable=book_info.get("is_negotiable", False),
                status=doc["status"],
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )
        )

    return PurchaseHistoryPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(skip + page_size) < total,
    )

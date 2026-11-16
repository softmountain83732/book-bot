# app/api/routes/sell_routes.py
"""Selling workflow API endpoints: photo staging, draft persistence, and publication."""
import os
import shutil
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from telegram import Bot

from app.api.deps import AuthContext, get_current_user, get_db
from app.config import settings
from app.services.sell_service import publish_book_listing, validate_sell_input

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sell", tags=["Sell"])

UPLOAD_STAGING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "staging")
os.makedirs(UPLOAD_STAGING_DIR, exist_ok=True)


class SellDraftPayload(BaseModel):
    title: str = ""
    major_slug: str = ""
    year: int = 1
    semester: Any = 1
    price: Optional[float] = None
    is_negotiable: bool = False
    condition: str = ""
    condition_details: Optional[str] = None
    photo_file_ids: List[str] = []


class PublishListingRequest(BaseModel):
    title: str
    major_slug: str
    year: int
    semester: Any
    price: Optional[float] = None
    is_negotiable: bool = False
    condition: str
    condition_details: Optional[str] = None
    photo_file_ids: List[str]


class PublishListingResponse(BaseModel):
    success: bool
    message: str
    book_id: Optional[str] = None


class StagedPhotoResponse(BaseModel):
    file_id: str
    url: str


@router.post("/upload-photo", response_model=StagedPhotoResponse)
async def upload_sell_photo(
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_current_user),
):
    """Upload a book photo from WebApp to Telegram servers to obtain an official Telegram file_id."""
    content_type = file.content_type or ""
    if not (content_type.startswith("image/") or file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
        raise HTTPException(status_code=400, detail="Invalid image file format")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo size must be under 10MB")

    # Send photo to channel or bot's own chat to obtain permanent Telegram file_id
    bot = Bot(token=settings.bot_token)
    user_id = auth.user_id

    try:
        # Send photo to user chat or channel to obtain valid telegram file_id
        # Sending to the user's private chat
        msg = await bot.send_photo(
            chat_id=user_id,
            photo=contents,
            caption="📸 HBTU Marketplace: စာအုပ်ဓာတ်ပုံ အဆင်သင့်ဖြစ်ပါပြီ။",
        )
        file_id = msg.photo[-1].file_id

        # Delete the temporary notification message so the user chat stays clean
        try:
            await bot.delete_message(chat_id=user_id, message_id=msg.message_id)
        except Exception:
            pass

        return StagedPhotoResponse(
            file_id=file_id,
            url=f"/api/v1/media/temp/{file_id}",
        )
    except Exception as exc:
        logger.exception("Failed to stage photo to Telegram for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=500,
            detail="ဓာတ်ပုံကို Telegram ပေါ်သို့ တင်ရာတွင် အမှားဖြစ်သွားပါသည်။ Bot ကို Private Chat တွင် အရင်ဆုံး Start လုပ်ထားပေးပါ။",
        )


@router.get("/draft")
async def get_sell_draft(
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieve seller's current draft from MongoDB."""
    doc = await db.sell_drafts.find_one({"_id": auth.user_id})
    return doc.get("draft") if doc else None


@router.post("/draft")
async def save_sell_draft(
    payload: SellDraftPayload,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Persist current form state to survive page refreshes."""
    now = datetime.now(timezone.utc)
    await db.sell_drafts.update_one(
        {"_id": auth.user_id},
        {
            "$set": {
                "draft": payload.model_dump(),
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return {"status": "saved"}


@router.delete("/draft")
async def clear_sell_draft(
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Clear saved sell draft."""
    await db.sell_drafts.delete_one({"_id": auth.user_id})
    return {"status": "cleared"}


@router.post("/publish", response_model=PublishListingResponse)
async def publish_listing_endpoint(
    body: PublishListingRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Validate and publish a new book listing to database and Telegram channel."""
    is_valid, err_msg, clean_data = validate_sell_input(
        title=body.title,
        major_slug=body.major_slug,
        year=body.year,
        semester=body.semester,
        price=body.price,
        is_negotiable=body.is_negotiable,
        condition=body.condition,
        photo_file_ids=body.photo_file_ids,
        condition_details=body.condition_details,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=err_msg)

    bot = Bot(token=settings.bot_token)
    user_info = auth.user_data or {}
    seller_username = user_info.get("username")

    success, message, book_id = await publish_book_listing(
        db=db,
        bot=bot,
        seller_id=auth.user_id,
        seller_username=seller_username,
        book_data=clean_data,
    )

    if not success:
        raise HTTPException(status_code=500, detail=message)

    # Clean up draft after successful publication
    await db.sell_drafts.delete_one({"_id": auth.user_id})

    return PublishListingResponse(
        success=True,
        message=message,
        book_id=str(book_id) if book_id else None,
    )

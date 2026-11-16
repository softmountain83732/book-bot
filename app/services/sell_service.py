# app/services/sell_service.py
"""Service for validating, creating, and publishing book listings to the channel."""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError

from app.config import settings
from app.keyboards.book_actions import purchase_keyboard
from app.services.audit_service import record_audit_event
from app.services.channel_service import build_book_caption, normalize_chat_id

logger = logging.getLogger(__name__)

VALID_MAJORS = {
    "ceit": "CEIT",
    "ep": "EP",
    "ec": "EC",
    "arch": "Architecture",
    "mc": "MC",
    "mech": "Mechanical",
    "civil": "Civil",
}

VALID_CONDITIONS = {
    "Used",
    "used",
    "အသစ်နီးပါး",
    "အတော်အသင့်ကောင်း",
    "အသုံးပြုထားသည်",
}


def validate_sell_input(
    title: str,
    major_slug: str,
    year: int,
    semester: Any,
    price: Optional[float],
    is_negotiable: bool,
    condition: str,
    photo_file_ids: List[str],
    condition_details: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate book listing fields according to university rules."""
    title = (title or "").strip()
    if not title or len(title) < 2 or len(title) > 120:
        return False, "စာအုပ်အမည်သည် အနည်းဆုံး ၂ လုံးမှ ၁၂၀ လုံးအတွင်း ဖြစ်ရပါမည်။", {}

    slug = (major_slug or "").lower().strip()
    if slug not in VALID_MAJORS:
        return False, "မေဂျာ မမှန်ကန်ပါ။", {}
    major_name = VALID_MAJORS[slug]

    if year not in [1, 2, 3, 4, 5, 6]:
        return False, "ပညာသင်နှစ်သည် Year 1 မှ Year 6 အတွင်း ဖြစ်ရပါမည်။", {}

    # Academic semester validation
    str_sem = str(semester).strip()
    if year == 2:
        valid_semesters = {"3", "4", "3 & 4", 3, 4}
    else:
        valid_semesters = {"1", "2", "1 & 2", 1, 2}

    if semester not in valid_semesters and str_sem not in valid_semesters:
        return False, f"Year {year} အတွက် Semester မမှန်ကန်ပါ။", {}

    if not is_negotiable:
        if price is None or price <= 0:
            return False, "ဈေးနှုန်း မသတ်မှတ်ရသေးပါ (သို့မဟုတ်) ဈေးညှိနှိုင်းဟု ရွေးချယ်ပေးပါ။", {}
        if price > 10_000_000:
            return False, "ဈေးနှုန်း ပမာဏများလွန်းနေပါသည်။", {}

    if condition not in VALID_CONDITIONS:
        # Accept if not empty
        if not condition or len(condition.strip()) < 2:
            return False, "စာအုပ်အခြေအနေကို ရွေးချယ်ပေးပါ။", {}

    # Validate optional condition_details
    cleaned_details: Optional[str] = None
    if condition_details is not None:
        det = condition_details.strip()
        if len(det) > 500:
            return False, "စာအုပ်အခြေအနေ အသေးစိတ်သည် စာလုံးရေ ၅၀၀ ထက် မကျော်ရပါ။", {}
        if det:
            cleaned_details = det

    if not photo_file_ids or len(photo_file_ids) == 0:
        return False, "အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ တင်ပေးရန် လိုအပ်ပါသည်။", {}

    if len(photo_file_ids) > 4:
        return False, "ဓာတ်ပုံ အများဆုံး ၄ ပုံသာ တင်နိုင်ပါသည်။", {}

    clean_data = {
        "title": title,
        "major": major_name,
        "major_slug": slug,
        "year": year,
        "semester": semester if isinstance(semester, (int, str)) else str(semester),
        "price": price if not is_negotiable else None,
        "is_negotiable": bool(is_negotiable),
        "condition": condition,
        "condition_details": cleaned_details,
        "photo_file_ids": photo_file_ids[:4],
        "photo_file_id": photo_file_ids[0],
    }
    return True, "", clean_data


async def publish_book_listing(
    db: AsyncDatabase,
    bot: Bot,
    seller_id: int,
    seller_username: Optional[str],
    book_data: Dict[str, Any],
) -> Tuple[bool, str, Optional[ObjectId]]:
    """Create book record in MongoDB and publish to Telegram Channel.
    
    Compatible with existing /sell bot conversation schema and channel messages.
    """
    now = datetime.now(timezone.utc)
    book_id = ObjectId()

    book = {
        "_id": book_id,
        "title": book_data["title"],
        "major": book_data["major"],
        "major_slug": book_data["major_slug"],
        "year": book_data["year"],
        "semester": book_data["semester"],
        "price": book_data.get("price"),
        "is_negotiable": book_data["is_negotiable"],
        "condition": book_data["condition"],
        "condition_details": book_data.get("condition_details"),
        "photo_file_id": book_data["photo_file_ids"][0],
        "photo_file_ids": book_data["photo_file_ids"],
        "seller_id": seller_id,
        "seller_username": seller_username,
        "status": "Available",
        "admin_hidden": False,
        "current_buyer_id": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await db.books.insert_one(book)
    except PyMongoError:
        logger.exception("Could not save new book listing for seller %s", seller_id)
        return False, "စာအုပ်အချက်အလက် သိမ်းဆည်းရာမှာ အမှားဖြစ်သွားပါသည်။", None

    # If no channel configured, finish here
    if not settings.channel_id:
        await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})
        return True, "စာအုပ် တင်ပြီးပါပြီ။ (Channel မသတ်မှတ်ထားပါ)", book_id

    channel_id = normalize_chat_id(settings.channel_id)
    photo_file_ids = book_data["photo_file_ids"]
    published_message_ids: List[int] = []

    try:
        if len(photo_file_ids) == 1:
            posted = await bot.send_photo(
                chat_id=channel_id,
                photo=photo_file_ids[0],
                caption=build_book_caption(book),
                reply_markup=purchase_keyboard(str(book_id), "Available"),
            )
            channel_message_id = posted.message_id
            published_message_ids.append(posted.message_id)
            channel_post_type = "photo"
            channel_photo_message_ids = [posted.message_id]
        else:
            media = [InputMediaPhoto(media=fid) for fid in photo_file_ids]
            media_messages = await bot.send_media_group(chat_id=channel_id, media=media)
            published_message_ids.extend(item.message_id for item in media_messages)

            info_post = await bot.send_message(
                chat_id=channel_id,
                text=build_book_caption(book),
                reply_markup=purchase_keyboard(str(book_id), "Available"),
            )
            channel_message_id = info_post.message_id
            published_message_ids.append(info_post.message_id)
            channel_post_type = "text"
            channel_photo_message_ids = [m.message_id for m in media_messages]

        await db.books.update_one(
            {"_id": book_id},
            {
                "$set": {
                    "channel_id": channel_id,
                    "channel_message_id": channel_message_id,
                    "channel_post_type": channel_post_type,
                    "channel_photo_message_ids": channel_photo_message_ids,
                    "channel_sync_error": False,
                }
            },
        )
    except Exception:
        logger.exception("Could not publish new book %s to channel %s", book_id, channel_id)
        for mid in published_message_ids:
            try:
                await bot.delete_message(chat_id=channel_id, message_id=mid)
            except TelegramError:
                pass
        await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})

    # Record audit log
    await record_audit_event(
        db,
        event_type="book_created",
        actor_id=seller_id,
        actor_role="seller",
        book_id=book_id,
        details={
            "title": book["title"],
            "major": book["major"],
            "year": book["year"],
            "semester": str(book["semester"]),
            "price": book["price"],
            "photo_count": len(photo_file_ids),
        },
    )

    return True, "စာအုပ် အောင်မြင်စွာ တင်ပြီးပါပြီ။", book_id

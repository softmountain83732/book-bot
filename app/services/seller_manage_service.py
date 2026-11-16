# app/services/seller_manage_service.py
"""Service for seller listing management: delist, relist, edit, and permanent channel delete."""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, Tuple
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from telegram import Bot
from telegram.error import TelegramError

from app.services.audit_service import record_audit_event
from app.services.channel_service import normalize_chat_id, update_book_channel

logger = logging.getLogger(__name__)


async def delete_channel_listing_posts(bot: Bot, book: Dict[str, Any]) -> bool:
    """Delete every Telegram message belonging to a single/album listing in the channel."""
    channel_id = book.get("channel_id")
    if not channel_id:
        return True

    message_ids = list(book.get("channel_photo_message_ids") or [])
    if book.get("channel_message_id"):
        message_ids.append(book["channel_message_id"])

    # Deduplicate message IDs
    message_ids = list(dict.fromkeys(int(m) for m in message_ids if m is not None))
    if not message_ids:
        return True

    success = True
    normalized_channel = normalize_chat_id(channel_id)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=normalized_channel, message_id=mid)
        except TelegramError:
            success = False
            logger.warning("Could not delete channel post %s for book %s", mid, book.get("_id"), exc_info=True)
    return success


async def seller_change_status(
    db: AsyncDatabase,
    bot: Bot,
    seller_id: int,
    book_id: ObjectId,
    target_status: str,
) -> Tuple[bool, str]:
    """Delist or Relist a book owned by the seller."""
    if target_status not in ["Delisted", "Available"]:
        return False, "မမှန်ကန်သော status ဖြစ်ပါသည်။"

    book = await db.books.find_one({"_id": book_id, "seller_id": seller_id})
    if not book:
        return False, "ဒီစာအုပ်ကို ရှာမတွေ့ပါ။"

    current_status = book.get("status")

    if target_status == "Delisted":
        if current_status != "Available" or book.get("admin_hidden"):
            return False, "Available ဖြစ်နေသော စာအုပ်ကိုသာ Delist လုပ်နိုင်ပါသည်။"
        expected_status = "Available"
        event_type = "seller_delist_listing"
        msg = "စာအုပ်ကို ယာယီ Delist လုပ်လိုက်ပါပြီ (ဝယ်ယူမှု ပိတ်ထားပါသည်)။"
    else:  # Relist
        if current_status != "Delisted" or book.get("admin_hidden"):
            return False, "Delisted ဖြစ်နေသော စာအုပ်ကိုသာ ပြန်လည်ရောင်းချနိုင်ပါသည်။"
        expected_status = "Delisted"
        event_type = "seller_relist_listing"
        msg = "စာအုပ်ကို ပြန်လည်ရောင်းချနိုင်ရန် Available အဖြစ် ဖွင့်လိုက်ပါပြီ။"

    now = datetime.now(timezone.utc)
    res = await db.books.update_one(
        {"_id": book_id, "seller_id": seller_id, "status": expected_status, "admin_hidden": {"$ne": True}},
        {"$set": {"status": target_status, "updated_at": now}},
    )

    if res.modified_count != 1:
        return False, "စာအုပ် Status ပြောင်းလဲသွားပါပြီ။"

    # Update channel post
    updated_book = {**book, "status": target_status}
    if updated_book.get("channel_message_id"):
        try:
            await update_book_channel(bot, updated_book, status=target_status)
            await db.books.update_one({"_id": book_id}, {"$unset": {"channel_sync_error": ""}})
        except Exception:
            logger.exception("Could not update channel post for book %s", book_id)
            await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})

    await record_audit_event(
        db,
        event_type=event_type,
        actor_id=seller_id,
        actor_role="seller",
        book_id=book_id,
        details={"from_status": expected_status, "to_status": target_status},
    )

    return True, msg


async def seller_permanently_delete_listing(
    db: AsyncDatabase,
    bot: Bot,
    seller_id: int,
    book_id: ObjectId,
) -> Tuple[bool, str]:
    """Permanently delete channel post and archive book document to 'Deleted'."""
    book = await db.books.find_one({"_id": book_id, "seller_id": seller_id})
    if not book or book.get("status") == "Deleted":
        return False, "ဒီစာအုပ်ကို မတွေ့တော့ပါ။"

    if book.get("status") == "Pending":
        return False, "ဝယ်ယူမှု စောင့်ဆိုင်းဆဲ (Pending) ဖြစ်နေသောကြောင့် ဖျက်၍ မရသေးပါ။"

    active_req = await db.purchase_requests.find_one({"book_id": book_id, "status": "Pending"})
    if active_req:
        return False, "Pending Purchase Request ရှိနေသောကြောင့် Post ကို မဖျက်နိုင်သေးပါ။"

    now = datetime.now(timezone.utc)
    res = await db.books.update_one(
        {"_id": book_id, "seller_id": seller_id, "status": {"$nin": ["Pending", "Deleted"]}},
        {"$set": {"status": "Deleted", "admin_hidden": True, "deleted_at": now, "deleted_by": seller_id, "updated_at": now}},
    )

    if res.modified_count != 1:
        return False, "စာအုပ် status ပြောင်းလဲသွားသောကြောင့် ဖျက်၍ မရတော့ပါ။"

    # Delete channel posts
    channel_deleted = await delete_channel_listing_posts(bot, book)
    channel_buttons_removed = False
    if not channel_deleted:
        try:
            await update_book_channel(bot, {**book, "status": "Deleted"}, status="Deleted")
            channel_buttons_removed = True
        except Exception:
            logger.exception("Could not disable actions on undeleted post for book %s", book_id)

    await db.books.update_one(
        {"_id": book_id},
        {
            "$set": {
                "channel_delete_error": not channel_deleted,
                "channel_deleted_at": now if channel_deleted else None,
                "channel_buttons_removed": channel_buttons_removed,
            }
        },
    )

    await record_audit_event(
        db,
        event_type="seller_delete_listing",
        actor_id=seller_id,
        actor_role="seller",
        book_id=book_id,
        details={"channel_deleted": channel_deleted},
    )

    return True, "စာအုပ် Channel Post ကို အပြီးဖျက်လိုက်ပါပြီ။"

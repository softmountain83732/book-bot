"""Route Telegram /start payloads from public listing buttons."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError
from telegram import User

from app.database.mongo import get_database

logger = logging.getLogger(__name__)


async def _favorite_from_deep_link(user: User, raw_book_id: str) -> tuple[str, bool, bool]:
    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        return "စာအုပ် ID မမှန်ကန်ပါ။", True, True

    db = get_database()
    try:
        registered = await db.users.find_one({"_id": user.id})
        if not registered:
            return "Bot ကို /start အရင်လုပ်ပေးပါ။", True, True
        book = await db.books.find_one({
            "_id": book_id,
            "status": "Available",
            "admin_hidden": {"$ne": True},
        })
        if not book:
            return "ဒီစာအုပ်ကို Favorites ထဲ သိမ်းလို့မရတော့ပါဘူး။", True, True
        if book.get("seller_id") == user.id:
            return "ကိုယ့်စာအုပ်ကို Favorites ထဲ ထည့်စရာမလိုပါဘူး။", True, True
        result = await db.favorites.update_one(
            {"user_id": user.id, "book_id": book_id},
            {"$setOnInsert": {
                "user_id": user.id,
                "book_id": book_id,
                "created_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    except DuplicateKeyError:
        return "❤️ ဒီစာအုပ်ကို Favorites ထဲ သိမ်းထားပြီးပါပြီ။", False, True
    except PyMongoError:
        logger.exception("Could not save favorite from deep link for user %s", user.id)
        return "Favorites သိမ်းဆည်းရာမှာ အမှားဖြစ်သွားပါတယ်။", True, True

    if result.upserted_id is None:
        return "❤️ ဒီစာအုပ်ကို Favorites ထဲ သိမ်းထားပြီးပါပြီ။", False, True
    return "❤️ Favorites ထဲ သိမ်းပြီးပါပြီ။", False, True


async def perform_start_action(
    bot,
    user: User,
    payload: str,
    user_data: dict,
) -> tuple[str, bool, bool]:
    """Return (feedback_text, show_alert, send_feedback_message)."""
    if not isinstance(payload, str) or "_" not in payload:
        return "Deep Link အချက်အလက် မမှန်ကန်ပါ။", True, True

    action, raw_book_id = payload.split("_", 1)
    if len(raw_book_id) != 24:
        return "စာအုပ် ID မမှန်ကန်ပါ။", True, True

    if action == "buy":
        from app.handlers.purchase import process_buy_book
        return await process_buy_book(bot, user, raw_book_id)

    if action == "fav":
        return await _favorite_from_deep_link(user, raw_book_id)

    if action == "report":
        from app.handlers.reports import open_report_form
        text, show_alert, form_was_sent = await open_report_form(
            bot=bot,
            user=user,
            raw_book_id=raw_book_id,
            user_data=user_data,
        )
        # open_report_form sends the actual reason-selection form itself.
        return text, show_alert, not form_was_sent

    return "မသိရှိသော Deep Link Action ဖြစ်ပါတယ်။", True, True

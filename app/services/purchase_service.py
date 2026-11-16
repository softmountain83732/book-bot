# app/services/purchase_service.py
"""Shared business logic for book purchasing, claim verification, and buyer cancellation."""
from datetime import datetime, timezone
import logging
from typing import Optional, Tuple
from bson import ObjectId
from bson.errors import InvalidId
from html import escape
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.keyboards.book_actions import buyer_cancel_keyboard, seller_control_keyboard
from app.services.audit_service import record_audit_event
from app.services.channel_service import update_book_channel

logger = logging.getLogger(__name__)


def get_price_display(book: dict) -> str:
    if book.get("is_negotiable"):
        return "ဈေးညှိနှိုင်း"
    price = book.get("price")
    if isinstance(price, (int, float)):
        return f"{price:,.0f} MMK"
    return "ဈေးနှုန်း မသတ်မှတ်ထားပါ"


def telegram_contact_link(user_id: int, username: Optional[str]) -> str:
    if username:
        return f"@{escape(username)}"
    return f'<a href="tg://user?id={user_id}">Telegram account</a>'


async def buy_book_claim(
    db: AsyncDatabase,
    bot: Optional[Bot],
    buyer_id: int,
    buyer_username: Optional[str],
    book_id: ObjectId,
) -> Tuple[bool, str, Optional[ObjectId]]:
    """Execute atomic availability claim and create purchase request.
    
    Returns: (success: bool, message: str, request_id: Optional[ObjectId])
    """
    now = datetime.now(timezone.utc)

    # 1. Check user exists
    buyer_record = await db.users.find_one({"_id": buyer_id})
    if buyer_record is None:
        return False, "အကောင့်ကို အရင်ဆုံး စာရင်းသွင်းပေးရန် လိုအပ်ပါသည်။", None

    # 2. Check book
    book = await db.books.find_one({"_id": book_id})
    if book is None:
        return False, "ဒီစာအုပ်ကို ရှာမတွေ့တော့ပါ။", None

    if book.get("admin_hidden"):
        return False, "ဒီစာအုပ်ကို လက်ရှိ ဝယ်ယူလို့မရပါဘူး။", None

    if book.get("seller_id") == buyer_id:
        return False, "ကိုယ့်စာအုပ်ကို ကိုယ်ဝယ်လို့ မရပါဘူး။", None

    status = book.get("status")

    # 3. Check existing active request
    existing_request = await db.purchase_requests.find_one(
        {"book_id": book_id, "buyer_id": buyer_id, "status": "Pending"},
        sort=[("created_at", -1)],
    )

    if status != "Available":
        if status == "Pending" and book.get("current_buyer_id") == buyer_id:
            msg = "ဒီစာအုပ်အတွက် သင့်ဝယ်ယူမှု Request ရှိပြီးသားပါ။"
        elif status == "Pending":
            msg = "ဒီစာအုပ်ကို တခြားဝယ်သူတစ်ယောက်က ဝယ်ယူရန် ညှိနှိုင်းနေပါပြီ။"
        elif status == "Sold":
            msg = "ဒီစာအုပ် ရောင်းထွက်သွားပါပြီ။"
        else:
            msg = "ဒီစာအုပ်ကို ဝယ်ယူလို့ မရတော့ပါဘူး။"
        return False, msg, None

    if existing_request and status == "Available":
        # Repair stale orphaned request
        await db.purchase_requests.update_one(
            {"_id": existing_request["_id"], "status": "Pending"},
            {"$set": {"status": "ReconciledStale", "updated_at": now}},
        )

    # 4. Atomic claim: Available -> Pending
    claim_res = await db.books.update_one(
        {
            "_id": book_id,
            "status": "Available",
            "admin_hidden": {"$ne": True},
        },
        {
            "$set": {
                "status": "Pending",
                "current_buyer_id": buyer_id,
                "updated_at": now,
            }
        },
    )

    if claim_res.modified_count != 1:
        latest = await db.books.find_one({"_id": book_id})
        if latest and latest.get("status") == "Pending":
            return False, "တခြားဝယ်သူတစ်ယောက်က အရင်ရယူသွားပါပြီ။", None
        return False, "ဒီစာအုပ်ကို လောလောဆယ် ဝယ်ယူလို့ မရတော့ပါ။", None

    # 5. Insert purchase request
    request_id = ObjectId()
    try:
        await db.purchase_requests.insert_one({
            "_id": request_id,
            "book_id": book_id,
            "seller_id": book["seller_id"],
            "buyer_id": buyer_id,
            "status": "Pending",
            "created_at": now,
            "updated_at": now,
        })
    except PyMongoError:
        logger.exception("Failed to insert purchase request for book %s", book_id)
        # Rollback book state
        await db.books.update_one(
            {"_id": book_id, "status": "Pending", "current_buyer_id": buyer_id},
            {"$set": {"status": "Available", "current_buyer_id": None, "updated_at": datetime.now(timezone.utc)}},
        )
        return False, "ဝယ်ယူမှုကို မှတ်တမ်းတင်ရာမှာ အမှားဖြစ်သွားပါသည်။ နောက်တစ်ကြိမ် ပြန်ကြိုးစားပါ။", None

    # 6. Audit log
    await record_audit_event(
        db,
        event_type="purchase_request_created",
        actor_id=buyer_id,
        actor_role="buyer",
        book_id=book_id,
        request_id=request_id,
        details={
            "title": str(book.get("title", "Untitled")),
            "price": book.get("price"),
            "seller_id": book["seller_id"],
        },
    )

    # 7. Notify channel & seller if bot instance is available
    if bot:
        try:
            await update_book_channel(bot, book, status="Pending")
            await db.books.update_one({"_id": book_id}, {"$unset": {"channel_sync_error": ""}})
        except Exception:
            logger.exception("Channel post update failed for book %s", book_id)
            await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})

        seller_msg = (
            "🔔 <b>စာအုပ်ဝယ်ယူရန် Request အသစ်ရောက်ရှိလာပါပြီ။</b>\n\n"
            f'📚 စာအုပ်: {escape(str(book.get("title", "Untitled")))}\n'
            f"💰 ဈေးနှုန်း: {escape(get_price_display(book))}\n"
            f"👤 ဝယ်သူ: {telegram_contact_link(buyer_id, buyer_username)}\n\n"
            "ဝယ်သူနဲ့ ဆက်သွယ်ပြီး အရောင်းအဝယ်အခြေအနေကို အောက်ပါ Button များမှ Update လုပ်ပေးပါ။"
        )
        try:
            seller_notice = await bot.send_message(
                chat_id=book["seller_id"],
                text=seller_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=seller_control_keyboard(str(book_id)),
            )
            await db.purchase_requests.update_one(
                {"_id": request_id, "status": "Pending"},
                {"$set": {"seller_message_id": seller_notice.message_id, "seller_message_chat_id": book["seller_id"]}},
            )
        except TelegramError:
            logger.exception("Could not notify seller %s for book %s", book["seller_id"], book_id)

    return True, "ဝယ်ယူမှု စတင်ပါပြီ။ ရောင်းသူထံသို့ အကြောင်းကြားထားပါသည်။", request_id


async def cancel_purchase_claim(
    db: AsyncDatabase,
    bot: Optional[Bot],
    buyer_id: int,
    request_id: ObjectId,
) -> Tuple[bool, str]:
    """Execute two-step safe cancellation from buyer.
    
    Returns: (success: bool, message: str)
    """
    now = datetime.now(timezone.utc)
    request = await db.purchase_requests.find_one({"_id": request_id, "buyer_id": buyer_id})
    if not request:
        return False, "ဒီ Purchase Request ကို မတွေ့ပါ။"

    if request.get("status") != "Pending":
        return False, "ဒီ Request ကို ဆုံးဖြတ်ပြီးသားဖြစ်လို့ Cancel လုပ်လို့မရတော့ပါ။"

    book_id = request.get("book_id")

    # Atomic release: Pending -> Available
    book_result = await db.books.update_one(
        {
            "_id": book_id,
            "status": "Pending",
            "current_buyer_id": buyer_id,
            "admin_hidden": {"$ne": True},
        },
        {
            "$set": {
                "status": "Available",
                "current_buyer_id": None,
                "updated_at": now,
            }
        },
    )

    if book_result.modified_count != 1:
        return False, "Seller သို့မဟုတ် Admin က အခြေအနေပြောင်းပြီးသားဖြစ်နိုင်တဲ့အတွက် Cancel မလုပ်နိုင်တော့ပါ။"

    # Close purchase request
    req_update = await db.purchase_requests.update_one(
        {"_id": request_id, "buyer_id": buyer_id, "status": "Pending"},
        {"$set": {"status": "CancelledByBuyer", "updated_at": now, "cancelled_by": buyer_id, "cancelled_at": now}},
    )

    # Re-read book to sync channel
    book = await db.books.find_one({"_id": book_id})

    # Audit log
    await record_audit_event(
        db,
        event_type="buyer_cancel_purchase_request",
        actor_id=buyer_id,
        actor_role="buyer",
        book_id=book_id if isinstance(book_id, ObjectId) else None,
        request_id=request_id,
        details={"title": str(book.get("title", "Untitled")) if book else "Untitled", "to_status": "Available"},
    )

    # Bot notifications
    if bot and book:
        try:
            await update_book_channel(bot, book, status=book.get("status"))
            await db.books.update_one({"_id": book_id}, {"$unset": {"channel_sync_error": ""}})
        except Exception:
            logger.exception("Could not sync channel after buyer cancellation for book %s", book_id)
            await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})

        seller_chat_id = request.get("seller_message_chat_id")
        seller_message_id = request.get("seller_message_id")
        if seller_chat_id and seller_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=seller_chat_id,
                    message_id=seller_message_id,
                    text=(
                        "↩️ <b>ဝယ်သူက Purchase Request ကို Cancel လုပ်လိုက်ပါပြီ။</b>\n\n"
                        f"📚 စာအုပ်: {escape(str(book.get('title', 'Untitled')) if book else 'Untitled')}\n"
                        "ဒီ Listing ကို အခြားဝယ်သူများ ပြန်လည်ဝယ်ယူနိုင်ပါပြီ။"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            except TelegramError:
                logger.debug("Could not update seller request msg %s", seller_message_id, exc_info=True)

    return True, "Purchase Request ကို Cancel လုပ်ပြီးပါပြီ။"

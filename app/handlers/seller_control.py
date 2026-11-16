import logging
from datetime import datetime, timezone
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
)

from app.database.mongo import get_database
from app.services.audit_service import record_audit_event
from app.services.channel_service import update_book_channel


logger = logging.getLogger(__name__)


ACTION_CONFIG = {
    "sold": {
        "new_status": "Sold",
        "request_status": "Sold",
        "seller_message": (
            "✅ စာအုပ်ကို ရောင်းထွက်သွားပြီဟု "
            "မှတ်တမ်းတင်ပြီးပါပြီ။"
        ),
        "buyer_message": (
            "✅ ရောင်းသူက ဒီစာအုပ်ကို ရောင်းထွက်သွားပြီဟု "
            "မှတ်တမ်းတင်လိုက်ပါပြီ။ ဝယ်ယူမှု Request ပိတ်သွားပါပြီ။"
        ),
    },
    "lost": {
        "new_status": "Available",
        "request_status": "BuyerUnresponsive",
        "seller_message": (
            "↩️ ဝယ်သူထံမှ တုံ့ပြန်မှုမရသောကြောင့် "
            "စာအုပ်ကို Available အဖြစ် ပြန်ဖွင့်ပြီးပါပြီ။"
        ),
        "buyer_message": (
            "စာအုပ်ရောင်းသူက သင့် Request ကို "
            "ပြန်လည်ပိတ်သိမ်းပြီး စာအုပ်ကို အခြားသူများ "
            "ပြန်လည်ဝယ်ယူနိုင်အောင် ဖွင့်လိုက်ပါပြီ။"
        ),
    },
    "release": {
        "new_status": "Available",
        "request_status": "ReleasedBySeller",
        "seller_message": (
            "↩️ သင့်ဆုံးဖြတ်ချက်အရ Listing ကို "
            "Available အဖြစ် ပြန်ဖွင့်ပြီးပါပြီ။"
        ),
        "buyer_message": (
            "ရောင်းသူက ဒီဝယ်ယူမှု Request ကို ပိတ်ပြီး "
            "စာအုပ်ကို အခြားသူများ ဝယ်ယူနိုင်အောင် ပြန်ဖွင့်လိုက်ပါပြီ။"
        ),
    },
    "cancel": {
        "new_status": "Cancelled",
        "request_status": "CancelledBySeller",
        "seller_message": (
            "🗑️ စာအုပ်ကို မရောင်းတော့ကြောင်း "
            "မှတ်တမ်းတင်ပြီးပါပြီ။"
        ),
        "buyer_message": (
            "🗑️ ရောင်းသူက ဒီစာအုပ်ကို မရောင်းတော့ကြောင်း "
            "ဆုံးဖြတ်လိုက်ပါပြီ။"
        ),
    },
}


async def _handle_continue_decision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db,
    book: dict,
    book_id: ObjectId,
    seller_id: int,
) -> None:
    """Record the seller's explicit decision to continue negotiating."""

    query = update.callback_query
    if query is None:
        return

    buyer_id = book.get("current_buyer_id")
    if buyer_id is None:
        await query.answer(
            "လက်ရှိ ဝယ်သူမရှိတော့ပါ။ Listing ကို ပြန်စစ်ပေးပါ။",
            show_alert=True,
        )
        return

    try:
        request = await db.purchase_requests.find_one(
            {
                "book_id": book_id,
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "status": "Pending",
            }
        )
    except PyMongoError:
        logger.exception(
            "Could not load purchase request for book %s.",
            book_id,
        )
        await query.answer(
            "ဝယ်ယူမှုအချက်အလက်ကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",
            show_alert=True,
        )
        return

    if request is None:
        await query.answer(
            "လက်ရှိ ဝယ်ယူမှု Request မရှိတော့ပါ။",
            show_alert=True,
        )
        return

    if request.get("seller_decision"):
        await query.answer(
            "သင့်ဆုံးဖြတ်ချက်ကို မှတ်တမ်းတင်ပြီးပါပြီ။",
            show_alert=True,
        )
        return

    now = datetime.now(timezone.utc)
    try:
        result = await db.purchase_requests.update_one(
            {
                "_id": request["_id"],
                "status": "Pending",
                "seller_decision": {"$exists": False},
            },
            {
                "$set": {
                    "seller_decision": "Continue",
                    "seller_decision_at": now,
                    "updated_at": now,
                }
            },
        )
    except PyMongoError:
        logger.exception(
            "Could not save seller's continue decision for book %s.",
            book_id,
        )
        await query.answer(
            "ဆုံးဖြတ်ချက်ကို သိမ်းဆည်းရာမှာ အမှားဖြစ်သွားပါတယ်။",
            show_alert=True,
        )
        return

    if result.modified_count != 1:
        await query.answer(
            "ဒီ Request အတွက် ဆုံးဖြတ်ချက်တစ်ခု မှတ်တမ်းတင်ပြီးသားပါ။",
            show_alert=True,
        )
        return

    await record_audit_event(
        db,
        event_type="seller_continue",
        actor_id=seller_id,
        actor_role="seller",
        book_id=book_id,
        request_id=request.get("_id"),
        details={
            "title": str(book.get("title", "Untitled")),
            "seller_decision": "Continue",
            "from_status": "Pending",
            "to_status": "Pending",
        },
    )

    await query.answer("ဆက်လက်ညှိနှိုင်းမည်ဟု မှတ်တမ်းတင်ပြီးပါပြီ။")

    title = escape(str(book.get("title", "Untitled")))
    if query.message:
        try:
            await query.edit_message_text(
                "✅ <b>ဆက်လက်ညှိနှိုင်းမည်ဟု အတည်ပြုပြီးပါပြီ။</b>\n\n"
                f"📚 စာအုပ်: <b>{title}</b>\n"
                "ဝယ်သူနဲ့ ဆက်လက်ညှိနှိုင်းနိုင်ပါတယ်။",
                parse_mode="HTML",
            )
        except TelegramError:
            logger.warning(
                "Could not edit continue-decision message for book %s.",
                book_id,
                exc_info=True,
            )

    try:
        await context.bot.send_message(
            chat_id=buyer_id,
            text=(
                "🤝 စာအုပ်ရောင်းသူက ဝယ်ယူမှုကို ဆက်လက်ညှိနှိုင်းမည်ဟု "
                "အတည်ပြုထားပါတယ်။ ရောင်းသူနဲ့ ဆက်သွယ်ပြီး "
                "အရောင်းအဝယ်ကို ဆက်လက်ညှိနှိုင်းနိုင်ပါတယ်။"
            ),
        )
    except TelegramError:
        logger.warning(
            "Could not notify buyer %s that seller will continue for book %s.",
            buyer_id,
            book_id,
            exc_info=True,
        )

    logger.info(
        "Seller %s chose to continue purchase request for book %s.",
        seller_id,
        book_id,
    )


async def seller_control_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query

    if query is None or not query.data:
        return

    seller = query.from_user
    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "Button data မမှန်ကန်ပါ။",
            show_alert=True,
        )
        return

    _, action, raw_book_id = parts

    if action not in ACTION_CONFIG and action != "continue":
        await query.answer(
            "ဒီလုပ်ဆောင်ချက်ကို မသိရှိပါ။",
            show_alert=True,
        )
        return

    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        await query.answer(
            "စာအုပ် ID မမှန်ကန်ပါ။",
            show_alert=True,
        )
        return

    db = get_database()

    try:
        book = await db.books.find_one({"_id": book_id})
    except PyMongoError:
        logger.exception("Could not load book %s for seller action.", book_id)
        await query.answer(
            "စာအုပ်အချက်အလက်ကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",
            show_alert=True,
        )
        return

    if book is None:
        await query.answer(
            "စာအုပ်ကို ရှာမတွေ့တော့ပါ။",
            show_alert=True,
        )
        return

    # Only the original seller can control this listing.
    if book.get("seller_id") != seller.id:
        await query.answer(
            "ဒီစာအုပ်ရဲ့ ရောင်းသူသာ အခြေအနေပြောင်းလို့ရပါတယ်။",
            show_alert=True,
        )
        return

    if book.get("status") != "Pending":
        await query.answer(
            "ဒီစာအုပ်ရဲ့ အခြေအနေ ပြောင်းလဲသွားပါပြီ။",
            show_alert=True,
        )
        return

    if action == "continue":
        await _handle_continue_decision(
            update=update,
            context=context,
            db=db,
            book=book,
            book_id=book_id,
            seller_id=seller.id,
        )
        return

    config = ACTION_CONFIG[action]
    now = datetime.now(timezone.utc)
    buyer_id = book.get("current_buyer_id")
    request_id = None
    if buyer_id is not None:
        try:
            pending_request = await db.purchase_requests.find_one(
                {
                    "book_id": book_id,
                    "buyer_id": buyer_id,
                    "seller_id": seller.id,
                    "status": "Pending",
                },
                sort=[("created_at", -1)],
            )
            if pending_request:
                request_id = pending_request.get("_id")
        except PyMongoError:
            logger.exception("Could not resolve purchase request id for book %s", book_id)

    new_status = config["new_status"]

    update_fields = {
        "status": new_status,
        "updated_at": now,
    }

    # Sold retains the buyer reference as the completed sale record.
    # Reopening/cancelling clears the active buyer assignment.
    if new_status in ("Available", "Cancelled"):
        update_fields["current_buyer_id"] = None

    try:
        result = await db.books.update_one(
            {
                "_id": book_id,
                "seller_id": seller.id,
                "status": "Pending",
                "current_buyer_id": buyer_id,
            },
            {
                "$set": update_fields,
            },
        )
    except PyMongoError:
        logger.exception(
            "Could not update seller status for book %s.",
            book_id,
        )
        await query.answer(
            "စာအုပ်အခြေအနေ ပြောင်းလဲရာမှာ အမှားဖြစ်သွားပါတယ်။",
            show_alert=True,
        )
        return

    if result.modified_count != 1:
        await query.answer(
            "အခြားလုပ်ဆောင်ချက်တစ်ခုကြောင့် "
            "စာအုပ်အခြေအနေ ပြောင်းလဲသွားပါပြီ။",
            show_alert=True,
        )
        return

    # Update request history separately from the book document.
    if buyer_id is not None:
        try:
            await db.purchase_requests.update_one(
                {
                    "book_id": book_id,
                    "buyer_id": buyer_id,
                    "status": "Pending",
                },
                {
                    "$set": {
                        "status": config["request_status"],
                        "updated_at": now,
                    }
                },
            )
        except PyMongoError:
            logger.exception(
                "Failed to update request history for book %s",
                book_id,
            )

    audit_event = {
        "sold": "seller_mark_sold",
        "lost": "seller_mark_unresponsive",
        "release": "seller_release_listing",
        "cancel": "seller_cancel_listing",
    }.get(action, "seller_listing_status_changed")
    await record_audit_event(
        db,
        event_type=audit_event,
        actor_id=seller.id,
        actor_role="seller",
        book_id=book_id,
        request_id=request_id,
        details={
            "title": str(book.get("title", "Untitled")),
            "action": action,
            "from_status": "Pending",
            "to_status": new_status,
            "request_status": config["request_status"],
        },
    )

    await query.answer("စာအုပ်အခြေအနေကို Update လုပ်ပြီးပါပြီ။")

    book["status"] = new_status
    book["current_buyer_id"] = update_fields.get(
        "current_buyer_id",
        buyer_id,
    )

    # Synchronize the public channel with the new database state.
    try:
        await update_book_channel(
            context.bot,
            book,
            status=new_status,
        )

        await db.books.update_one(
            {"_id": book_id},
            {
                "$unset": {"channel_sync_error": ""},
            },
        )

    except Exception:
        logger.exception(
            "Failed to synchronize channel for book %s",
            book_id,
        )

        await db.books.update_one(
            {"_id": book_id},
            {
                "$set": {"channel_sync_error": True},
            },
        )

    # Inform the previous buyer where possible.
    if buyer_id is not None:
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=config["buyer_message"],
            )
        except TelegramError:
            logger.warning(
                "Could not notify buyer %s about book %s",
                buyer_id,
                book_id,
                exc_info=True,
            )

    # Remove the controls from the seller's old message.
    if query.message:
        try:
            title = escape(str(book.get("title", "Untitled")))
            await query.edit_message_text(
                f"{config['seller_message']}\n\n📚 စာအုပ်: <b>{title}</b>",
                parse_mode="HTML",
            )
        except TelegramError:
            logger.warning(
                "Could not update seller control message for book %s",
                book_id,
                exc_info=True,
            )

    logger.info(
        "Seller %s changed book %s to status %s using action %s.",
        seller.id,
        book_id,
        new_status,
        action,
    )


def build_seller_control_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        seller_control_callback,
        pattern=r"^seller:(sold|lost|release|cancel|continue):[0-9a-fA-F]{24}$",
    )

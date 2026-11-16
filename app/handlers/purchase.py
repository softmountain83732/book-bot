#app/handlers/purchase.py
import logging
from datetime import datetime, timezone
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
)

from app.database.mongo import get_database
from app.services.audit_service import record_audit_event
from app.keyboards.book_actions import buyer_cancel_keyboard, seller_control_keyboard
from app.services.channel_service import format_semester, update_book_channel


logger = logging.getLogger(__name__)


def telegram_contact(user_id: int, username: str | None) -> str:
    if username:
        return f"@{escape(username)}"

    return (
        f'<a href="tg://user?id={user_id}">'
        "Telegram account"
        "</a>"
    )


def get_price_text(book: dict) -> str:
    if book.get("is_negotiable"):
        return "ဈေးညှိနှိုင်း"

    price = book.get("price")

    if isinstance(price, (int, float)):
        return f"{price:,.0f} MMK"

    return "ဈေးနှုန်း မသတ်မှတ်ထားပါ"


async def process_buy_book(
    bot,
    buyer: User,
    raw_book_id: str,
) -> tuple[str, bool, bool]:
    """
    Process a purchase request for both deep-link and callback entry points.

    Returns:
        (message, show_alert, send_message_to_buyer)

    On a successful purchase, the buyer receives a private message containing
    the seller's contact, so an extra result message is not required.
    """

    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        return "စာအုပ် ID မမှန်ကန်ပါ။", True, True

    db = get_database()

    try:
        buyer_record = await db.users.find_one({"_id": buyer.id})
    except PyMongoError:
        logger.exception(
            "Could not load buyer %s before purchasing book %s.",
            buyer.id,
            book_id,
        )
        return (
            "ဝယ်ယူမှုကို စစ်ဆေးရာမှာ အမှားဖြစ်သွားပါတယ်။ "
            "ခဏနေမှ ပြန်ကြိုးစားပေးပါ။",
            True,
            True,
        )

    if buyer_record is None:
        return (
            "ဒီ Bot ကို Private Chat မှာ Start လုပ်ပြီးမှ "
            "ဝယ်ယူနိုင်ပါတယ်။",
            True,
            True,
        )

    try:
        book = await db.books.find_one({"_id": book_id})
    except PyMongoError:
        logger.exception("Could not load book %s.", book_id)
        return (
            "စာအုပ်အချက်အလက်ကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",
            True,
            True,
        )

    if book is None:
        return "ဒီစာအုပ်ကို ရှာမတွေ့တော့ပါ။", True, True

    if book.get("admin_hidden"):
        return "ဒီစာအုပ်ကို လက်ရှိ ဝယ်ယူလို့မရပါဘူး။", True, True

    if book.get("seller_id") == buyer.id:
        return "ကိုယ့်စာအုပ်ကို ကိုယ်ဝယ်လို့ မရပါဘူး။", True, True

    status = book.get("status")

    # A second tap must never create a second active request for the same buyer/book.
    try:
        existing_request = await db.purchase_requests.find_one(
            {"book_id": book_id, "buyer_id": buyer.id, "status": "Pending"},
            sort=[("created_at", -1)],
        )
    except PyMongoError:
        logger.exception("Could not check existing purchase request for buyer %s/book %s", buyer.id, book_id)
        return "ဝယ်ယူမှုအခြေအနေကို စစ်ဆေးရာမှာ အမှားဖြစ်သွားပါတယ်။", True, True

    if status != "Available":
        if (
            status == "Pending"
            and book.get("current_buyer_id") == buyer.id
        ):
            message = (
                "ဒီစာအုပ်အတွက် သင့်ဝယ်ယူမှု Request ရှိပြီးသားပါ။ "
                "Bot Private Chat မှာရှိတဲ့ Purchase Request Message ကနေ Cancel လုပ်နိုင်ပါတယ်။"
            )
        elif status == "Pending":
            message = (
                "ဒီစာအုပ်ကို တခြားဝယ်သူတစ်ယောက်က "
                "ဝယ်ယူရန် ညှိနှိုင်းနေပါပြီ။"
            )
        elif status == "Sold":
            message = "ဒီစာအုပ် ရောင်းထွက်သွားပါပြီ။"
        else:
            message = "ဒီစာအုပ်ကို ဝယ်ယူလို့ မရတော့ပါဘူး။"

        return message, True, True

    if existing_request and status == "Available":
        # Repair a stale orphaned request left by an interrupted earlier update.
        try:
            await db.purchase_requests.update_one(
                {"_id": existing_request["_id"], "status": "Pending"},
                {"$set": {"status": "ReconciledStale", "updated_at": datetime.now(timezone.utc)}},
            )
        except PyMongoError:
            logger.exception("Could not reconcile stale request %s", existing_request.get("_id"))
            return "အရင် Purchase Request ကို စစ်ဆေးနေပါတယ်။ ခဏနေမှ ပြန်ကြိုးစားပါ။", True, True

    now = datetime.now(timezone.utc)

    # Atomic claim: only one buyer can change Available -> Pending.
    try:
        result = await db.books.update_one(
            {
                "_id": book_id,
                "status": "Available",
                "admin_hidden": {"$ne": True},
            },
            {
                "$set": {
                    "status": "Pending",
                    "current_buyer_id": buyer.id,
                    "updated_at": now,
                }
            },
        )
    except PyMongoError:
        logger.exception(
            "Could not claim book %s for buyer %s.",
            book_id,
            buyer.id,
        )
        return (
            "ဝယ်ယူမှုကို စတင်ရာမှာ အမှားဖြစ်သွားပါတယ်။ "
            "ခဏနေမှ ပြန်ကြိုးစားပေးပါ။",
            True,
            True,
        )

    if result.modified_count != 1:
        try:
            latest_book = await db.books.find_one({"_id": book_id})
        except PyMongoError:
            logger.exception("Could not re-check book %s after a failed atomic claim", book_id)
            return "စာအုပ်အခြေအနေကို စစ်ဆေးရာမှာ အမှားဖြစ်သွားပါတယ်။", True, True

        if latest_book and latest_book.get("status") == "Pending":
            message = "တခြားဝယ်သူတစ်ယောက်က အရင်ရယူသွားပါပြီ။"
        else:
            message = "ဒီစာအုပ်ကို လောလောဆယ် ဝယ်ယူလို့ မရတော့ပါ။"

        return message, True, True

    request_id = ObjectId()

    try:
        await db.purchase_requests.insert_one({
            "_id": request_id,
            "book_id": book_id,
            "seller_id": book["seller_id"],
            "buyer_id": buyer.id,
            "status": "Pending",
            "created_at": now,
            "updated_at": now,
        })

    except PyMongoError:
        logger.exception(
            "Failed to create purchase request for book %s.",
            book_id,
        )

        await db.books.update_one(
            {
                "_id": book_id,
                "status": "Pending",
                "current_buyer_id": buyer.id,
            },
            {
                "$set": {
                    "status": "Available",
                    "current_buyer_id": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        return (
            "ဝယ်ယူမှုကို မှတ်တမ်းတင်ရာမှာ အမှားဖြစ်သွားပါတယ်။ "
            "နောက်တစ်ကြိမ် ပြန်ကြိုးစားပါ။",
            True,
            True,
        )

    await record_audit_event(
        db,
        event_type="purchase_request_created",
        actor_id=buyer.id,
        actor_role="buyer",
        book_id=book_id,
        request_id=request_id,
        details={
            "title": str(book.get("title", "Untitled")),
            "from_status": "Available",
            "to_status": "Pending",
        },
    )

    try:
        seller_record = await db.users.find_one(
            {"_id": book["seller_id"]}
        )
    except PyMongoError:
        logger.exception(
            "Could not load seller record for book %s.",
            book_id,
        )
        seller_record = None

    seller_username = (
        seller_record.get("username")
        if seller_record
        else book.get("seller_username")
    )

    seller_contact = telegram_contact(
        book["seller_id"],
        seller_username,
    )

    buyer_message = (
        "📚 <b>သင့်ဝယ်ယူမှု Request ကို လက်ခံလိုက်ပါပြီ။</b>\n\n"
        f'စာအုပ်: {escape(str(book.get("title", "Untitled")))}\n'
        f'ဈေးနှုန်း: {escape(get_price_text(book))}\n'
        f'Major: {escape(str(book.get("major", "N/A")))}\n'
        f'Year: {escape(str(book.get("year", "N/A")))}\n'
        f'Semester: {escape(format_semester(book.get("year"), book.get("semester", "N/A")))}\n\n'
        f"👤 ရောင်းသူ: {seller_contact}\n\n"
        "ရောင်းသူကို ဆက်သွယ်ပြီး အရောင်းအဝယ်ကို "
        "ညှိနှိုင်းနိုင်ပါပြီ။"
    )

    # Send the buyer's private message before updating the channel post.
    try:
        buyer_notice = await bot.send_message(
            chat_id=buyer.id,
            text=buyer_message,
            parse_mode=ParseMode.HTML,
        )
        try:
            await db.purchase_requests.update_one(
                {"_id": request_id, "status": "Pending"},
                {"$set": {"buyer_message_id": buyer_notice.message_id, "buyer_message_chat_id": buyer.id}},
            )
        except PyMongoError:
            logger.exception("Buyer message sent but its Telegram message ID could not be stored for request %s", request_id)

    except TelegramError:
        logger.exception(
            "Could not message buyer %s for book %s.",
            buyer.id,
            book_id,
        )

        now_failed = datetime.now(timezone.utc)

        await db.books.update_one(
            {
                "_id": book_id,
                "status": "Pending",
                "current_buyer_id": buyer.id,
            },
            {
                "$set": {
                    "status": "Available",
                    "current_buyer_id": None,
                    "updated_at": now_failed,
                }
            },
        )

        await db.purchase_requests.update_one(
            {"_id": request_id},
            {
                "$set": {
                    "status": "NotificationFailed",
                    "updated_at": now_failed,
                }
            },
        )

        return (
            "Bot က သင့်ကို Private Message မပို့နိုင်ပါ။ "
            "Bot ကို Start လုပ်ထားကြောင်း စစ်ပြီး ပြန်ကြိုးစားပါ။",
            True,
            True,
        )

    # Update the channel listing to Pending.
    book["status"] = "Pending"
    book["current_buyer_id"] = buyer.id

    try:
        await update_book_channel(
            bot,
            book,
            status="Pending",
        )

        await db.books.update_one(
            {"_id": book_id},
            {"$unset": {"channel_sync_error": ""}},
        )

    except Exception:
        logger.exception(
            "Failed to update pending channel post for book %s.",
            book_id,
        )

        await db.books.update_one(
            {"_id": book_id},
            {"$set": {"channel_sync_error": True}},
        )

    buyer_contact = telegram_contact(
        buyer.id,
        buyer.username,
    )

    seller_message = (
        "🔔 <b>စာအုပ်ဝယ်ယူရန် Request အသစ်ရောက်ရှိလာပါပြီ။</b>\n\n"
        f'📚 စာအုပ်: {escape(str(book.get("title", "Untitled")))}\n'
        f"💰 ဈေးနှုန်း: {escape(get_price_text(book))}\n"
        f"👤 ဝယ်သူ: {buyer_contact}\n\n"
        "ဝယ်သူနဲ့ ဆက်သွယ်ပြီး အရောင်းအဝယ်အခြေအနေကို "
        "အောက်ပါ Button များမှ Update လုပ်ပေးပါ။"
    )

    try:
        seller_notice = await bot.send_message(
            chat_id=book["seller_id"],
            text=seller_message,
            parse_mode=ParseMode.HTML,
            reply_markup=seller_control_keyboard(str(book_id)),
        )
        try:
            await db.purchase_requests.update_one(
                {"_id": request_id, "status": "Pending"},
                {"$set": {"seller_message_id": seller_notice.message_id, "seller_message_chat_id": book["seller_id"]}},
            )
        except PyMongoError:
            logger.exception("Seller message sent but its Telegram message ID could not be stored for request %s", request_id)

    except TelegramError:
        logger.exception(
            "Could not notify seller %s for book %s.",
            book["seller_id"],
            book_id,
        )

    # Enable buyer cancellation only after the listing and seller notice have
    # been processed, so a fast cancellation cannot be overwritten by this
    # purchase flow's remaining setup operations.
    buyer_message_id = None
    try:
        if 'buyer_notice' in locals():
            buyer_message_id = buyer_notice.message_id
        if buyer_message_id is not None:
            await bot.edit_message_reply_markup(
                chat_id=buyer.id,
                message_id=buyer_message_id,
                reply_markup=buyer_cancel_keyboard(str(request_id)),
            )
    except TelegramError:
        logger.exception("Could not activate buyer cancel button for request %s", request_id)

    return (
        "ဝယ်ယူမှု စတင်ပါပြီ။ ရောင်းသူ၏ Contact ကို "
        "Bot Private Chat ထဲမှာ ကြည့်နိုင်ပါတယ်။",
        False,
        False,
    )


async def _edit_buyer_request_message(query, text: str, reply_markup=None) -> None:
    """Update the request message without making Telegram edit failures fatal."""
    if query.message is None:
        return
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except TelegramError:
        logger.debug("Could not edit buyer request message", exc_info=True)


async def _buyer_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return

    parts = query.data.split(":")
    if len(parts) != 4 or parts[:2] != ["purchase", "cancel"]:
        await query.answer("Button အချက်အလက် မမှန်ကန်ပါ။", show_alert=True)
        return

    action, raw_request_id = parts[2], parts[3]
    try:
        request_id = ObjectId(raw_request_id)
    except (InvalidId, TypeError):
        await query.answer("Purchase Request ID မမှန်ကန်ပါ။", show_alert=True)
        return

    db = get_database()
    buyer_id = query.from_user.id
    try:
        request = await db.purchase_requests.find_one({"_id": request_id, "buyer_id": buyer_id})
    except PyMongoError:
        logger.exception("Could not load purchase request %s for buyer %s", request_id, buyer_id)
        await query.answer("Purchase Request ကို စစ်ဆေးရာမှာ Database အမှားဖြစ်သွားပါတယ်။", show_alert=True)
        return
    if not request:
        await query.answer("ဒီ Purchase Request ကို မတွေ့ပါ။", show_alert=True)
        return

    if action == "ask":
        if request.get("status") != "Pending":
            await query.answer("ဒီ Request ကို ဆုံးဖြတ်ပြီးသားဖြစ်လို့ Cancel လုပ်လို့မရတော့ပါ။", show_alert=True)
            return
        confirm_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ဟုတ်ကဲ့၊ Cancel လုပ်မည်", callback_data=f"purchase:cancel:confirm:{request_id}")],
            [InlineKeyboardButton("↩️ မလုပ်တော့ပါ", callback_data=f"purchase:cancel:keep:{request_id}")],
        ])
        await query.answer()
        await _edit_buyer_request_message(
            query,
            "⚠️ <b>Purchase Request ကို Cancel လုပ်မှာ သေချာပါသလား။</b>\n\n"
            "Confirm လုပ်မှ Request ပိတ်ပြီး စာအုပ်ကို Available ပြန်ဖွင့်ပေးပါမယ်။",
            reply_markup=confirm_markup,
        )
        return

    if action == "keep":
        if request.get("status") != "Pending":
            await query.answer("ဒီ Request အခြေအနေ ပြောင်းလဲသွားပါပြီ။", show_alert=True)
            return
        await query.answer("Cancel မလုပ်တော့ပါဘူး။")
        await _edit_buyer_request_message(
            query,
            "⏳ <b>Purchase Request Pending</b>\n\n"
            "Seller ရဲ့ တုံ့ပြန်မှုကို စောင့်နေဆဲဖြစ်ပါတယ်။",
            reply_markup=buyer_cancel_keyboard(str(request_id)),
        )
        return

    if action != "confirm":
        await query.answer("မသိရှိသော Cancel Action ဖြစ်ပါတယ်။", show_alert=True)
        return

    if request.get("status") != "Pending":
        await query.answer("ဒီ Request ကို ဆုံးဖြတ်ပြီးသားဖြစ်လို့ Cancel လုပ်လို့မရတော့ပါ။", show_alert=True)
        return

    book_id = request.get("book_id")
    now = datetime.now(timezone.utc)
    try:
        # The book transition is the single-winner guard shared with Seller/Admin actions.
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
    except PyMongoError:
        logger.exception("Could not release book %s after buyer cancellation", book_id)
        await query.answer("Cancel လုပ်ရာမှာ Database အမှားဖြစ်သွားပါတယ်။ ပြန်ကြိုးစားပါ။", show_alert=True)
        return

    if book_result.modified_count != 1:
        await query.answer(
            "Seller သို့မဟုတ် Admin က အခြေအနေပြောင်းပြီးသားဖြစ်နိုင်တဲ့အတွက် Cancel မလုပ်နိုင်တော့ပါ။",
            show_alert=True,
        )
        return

    request_closed = False
    for attempt in range(2):
        try:
            request_result = await db.purchase_requests.update_one(
                {"_id": request_id, "buyer_id": buyer_id, "status": "Pending"},
                {"$set": {"status": "CancelledByBuyer", "updated_at": now, "cancelled_by": buyer_id, "cancelled_at": now}},
            )
            request_closed = request_result.modified_count == 1
            if not request_closed:
                latest_request = await db.purchase_requests.find_one({"_id": request_id, "buyer_id": buyer_id})
                request_closed = bool(latest_request and latest_request.get("status") == "CancelledByBuyer")
            break
        except PyMongoError:
            logger.exception("Could not close request %s after releasing book %s (attempt %s)", request_id, book_id, attempt + 1)
            try:
                latest_request = await db.purchase_requests.find_one({"_id": request_id, "buyer_id": buyer_id})
                if latest_request and latest_request.get("status") == "CancelledByBuyer":
                    request_closed = True
                    break
            except PyMongoError:
                logger.exception("Could not verify request %s after cancellation write error", request_id)

    if not request_closed:
        logger.critical("Book %s was released but request %s could not be marked CancelledByBuyer", book_id, request_id)
        await query.answer("စာအုပ်ကို ပြန်ဖွင့်ပြီးပါပြီ၊ ဒါပေမဲ့ Request History ကို Update မလုပ်နိုင်သေးပါ။ Admin ကို အသိပေးထားပါတယ်။", show_alert=True)
        return

    try:
        book = await db.books.find_one({"_id": book_id})
    except PyMongoError:
        logger.exception("Could not reload book %s after buyer cancellation", book_id)
        book = None

    if book:
        try:
            # Another buyer may have claimed the listing immediately after this
            # cancellation released it. Always sync the latest DB status.
            await update_book_channel(context.bot, book, status=book.get("status"))
            await db.books.update_one({"_id": book_id}, {"$unset": {"channel_sync_error": ""}})
        except Exception:
            logger.exception("Could not synchronize channel listing for book %s after buyer cancellation", book_id)
            try:
                await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})
            except PyMongoError:
                logger.exception("Could not record channel sync error for book %s", book_id)

    await record_audit_event(
        db,
        event_type="buyer_cancel_purchase_request",
        actor_id=buyer_id,
        actor_role="buyer",
        book_id=book_id if isinstance(book_id, ObjectId) else None,
        request_id=request_id,
        details={"title": str(book.get("title", "Untitled")) if book else "Untitled", "to_status": "Available"},
    )

    # Close the seller's old request card when its Telegram message reference is available.
    seller_chat_id = request.get("seller_message_chat_id")
    seller_message_id = request.get("seller_message_id")
    if seller_chat_id and seller_message_id:
        try:
            await context.bot.edit_message_text(
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
            logger.debug("Could not update seller request message %s", seller_message_id, exc_info=True)

    await query.answer("Purchase Request ကို Cancel လုပ်ပြီးပါပြီ။")
    await _edit_buyer_request_message(
        query,
        "✅ <b>Purchase Request ကို Cancel လုပ်ပြီးပါပြီ။</b>\n\n"
        "စာအုပ်ကို Available အဖြစ် ပြန်ဖွင့်ထားပါတယ်။",
        reply_markup=None,
    )


async def purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    if query.data.startswith("purchase:cancel:"):
        await _buyer_cancel_callback(update, context)
        return

    raw_book_id = query.data.removeprefix("buy:")
    message, show_alert, send_message_to_buyer = await process_buy_book(
        bot=context.bot,
        buyer=query.from_user,
        raw_book_id=raw_book_id,
    )
    await query.answer(message, show_alert=show_alert)


def build_purchase_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        purchase_callback,
        pattern=r"^(?:buy:[0-9a-fA-F]{24}|purchase:cancel:(?:ask|confirm|keep):[0-9a-fA-F]{24})$",
    )

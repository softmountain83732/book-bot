import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import Application

from app.config import settings
from app.database.mongo import get_database
from app.services.audit_service import record_audit_event
from app.keyboards.book_actions import seller_control_keyboard
from app.keyboards.pending_lifecycle import pending_decision_keyboard


logger = logging.getLogger(__name__)

WARNING_AFTER = timedelta(hours=22)
DECISION_AFTER = timedelta(hours=24)
ESCALATION_AFTER = timedelta(hours=48)
POLL_INTERVAL_SECONDS = 60
FAILED_DELIVERY_RETRY_AFTER = timedelta(minutes=15)



def _as_utc(value: datetime) -> datetime:
    """PyMongo may return naive datetimes; treat those as UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _load_active_pending_book(db, request: dict) -> dict | None:
    """Return the listing only if this request still owns its Pending state."""

    book_id = request.get("book_id")
    buyer_id = request.get("buyer_id")
    seller_id = request.get("seller_id")

    if book_id is None or buyer_id is None or seller_id is None:
        return None

    book = await db.books.find_one({"_id": book_id})
    if book is None:
        return None

    if book.get("status") != "Pending":
        return None

    if book.get("current_buyer_id") != buyer_id:
        return None

    if book.get("seller_id") != seller_id:
        return None

    return book


async def _get_user_label(db, telegram_user_id: int | None) -> str:
    """Resolve a Telegram username or display name without exposing numeric IDs."""

    if telegram_user_id is None:
        return "မသိရှိပါ"

    try:
        user_doc = await db.users.find_one({"_id": telegram_user_id})
    except PyMongoError:
        logger.exception(
            "Could not find user details for Telegram user %s.",
            telegram_user_id,
        )
        return "Username မရရှိပါ"

    if not user_doc:
        return "Username မရရှိပါ"

    username = (
        user_doc.get("username")
        or user_doc.get("telegram_username")
        or user_doc.get("user_name")
    )
    if username:
        cleaned = str(username).strip().removeprefix("@")
        if cleaned:
            return f"@{escape(cleaned)}"

    display_name = user_doc.get("first_name") or user_doc.get("name")
    if display_name:
        return escape(str(display_name))

    return "Username မရှိပါ"


def _should_retry(request: dict, attempt_field: str, now: datetime) -> bool:
    """Avoid retrying failed Telegram deliveries every polling cycle."""

    last_attempt = request.get(attempt_field)
    if not isinstance(last_attempt, datetime):
        return True

    return now - _as_utc(last_attempt) >= FAILED_DELIVERY_RETRY_AFTER


async def _send_seller_stage(
    *,
    application: Application,
    db,
    request: dict,
    seller_id: int,
    text: str,
    marker_field: str,
    attempt_field: str,
    error_field: str,
    reply_markup=None,
    audit_title: str | None = None,
) -> bool:
    """Send one seller notification and persist its successful delivery marker."""

    if request.get(marker_field):
        return True

    now = datetime.now(timezone.utc)
    if not _should_retry(request, attempt_field, now):
        return False

    try:
        await application.bot.send_message(
            chat_id=seller_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except TelegramError as exc:
        logger.warning(
            "Could not deliver lifecycle message '%s' to seller %s for request %s.",
            marker_field,
            seller_id,
            request.get("_id"),
            exc_info=True,
        )
        try:
            await db.purchase_requests.update_one(
                {"_id": request["_id"], "status": "Pending"},
                {
                    "$set": {
                        attempt_field: now,
                        error_field: str(exc)[:500],
                    }
                },
            )
            request[attempt_field] = now
        except PyMongoError:
            logger.exception(
                "Could not save lifecycle delivery failure for request %s.",
                request.get("_id"),
            )
        return False

    try:
        result = await db.purchase_requests.update_one(
            {
                "_id": request["_id"],
                "status": "Pending",
                marker_field: {"$exists": False},
            },
            {
                "$set": {marker_field: now},
                "$unset": {
                    attempt_field: "",
                    error_field: "",
                },
            },
        )
    except PyMongoError:
        logger.exception(
            "Message sent, but lifecycle marker could not be saved for request %s.",
            request.get("_id"),
        )
        return False

    if result.modified_count == 1:
        request[marker_field] = now
        request.pop(attempt_field, None)
        request.pop(error_field, None)
        logger.info(
            "Lifecycle notification '%s' sent for request %s.",
            marker_field,
            request.get("_id"),
        )
        event_type = {
            "seller_warning_sent_at": "seller_warning_sent",
            "seller_decision_requested_at": "seller_decision_requested",
        }.get(marker_field)
        if event_type:
            await record_audit_event(
                db,
                event_type=event_type,
                actor_id=None,
                actor_role="system",
                book_id=request.get("book_id"),
                request_id=request.get("_id"),
                details={
                    "title": audit_title or "Untitled",
                    "seller_id": seller_id,
                    "stage": marker_field,
                },
            )
        return True

    # The request may have been closed while the Telegram message was sending.
    return False


async def _post_url(application: Application, book: dict) -> str | None:
    """Build a direct Telegram link to the listing when available."""

    channel_id = book.get("channel_id")
    message_id = book.get("channel_message_id")
    if not channel_id or not message_id:
        return None

    channel_username = None
    try:
        chat = await application.bot.get_chat(channel_id)
        channel_username = getattr(chat, "username", None)
    except TelegramError:
        logger.debug(
            "Could not resolve channel for book %s.",
            book.get("_id"),
            exc_info=True,
        )

    if not channel_username and isinstance(channel_id, str):
        candidate = channel_id.strip()
        if candidate.startswith("@"):
            channel_username = candidate[1:]

    if channel_username:
        return f"https://t.me/{channel_username}/{int(message_id)}"

    channel_id_text = str(channel_id).strip()
    if channel_id_text.startswith("-100") and channel_id_text[4:].isdigit():
        return f"https://t.me/c/{channel_id_text[4:]}/{int(message_id)}"

    return None


async def _escalate_to_admins(
    application: Application,
    db,
    request: dict,
    book: dict,
) -> None:
    """Notify admins once when a Pending request has no seller decision by 48h."""

    if request.get("admin_escalated_at"):
        return

    admin_ids = settings.admin_telegram_ids
    now = datetime.now(timezone.utc)

    if not admin_ids:
        # Record only that we logged the missing configuration, not that an
        # escalation was delivered. If configuration is corrected, later polls
        # will still attempt to notify admins.
        if not request.get("admin_escalation_config_missing_logged_at"):
            logger.error(
                "Cannot escalate Pending request %s: ADMIN_IDS is empty.",
                request.get("_id"),
            )
            try:
                await db.purchase_requests.update_one(
                    {"_id": request["_id"], "status": "Pending"},
                    {
                        "$set": {
                            "admin_escalation_config_missing_logged_at": now
                        }
                    },
                )
            except PyMongoError:
                logger.exception(
                    "Could not store missing ADMIN_IDS marker for request %s.",
                    request.get("_id"),
                )
        return

    if not _should_retry(
        request,
        "admin_escalation_last_attempt_at",
        now,
    ):
        return

    seller_label = await _get_user_label(db, request.get("seller_id"))
    title = escape(str(book.get("title", "Untitled")))
    message = (
        "⚠️ <b>Pending Purchase Admin Escalation</b>\n\n"
        f"📚 စာအုပ်: <b>{title}</b>\n"
        "⏳ ဝယ်ယူမှု Pending ဖြစ်နေသည်မှာ 48 နာရီကျော်ပါပြီ။\n"
        f"👤 ရောင်းသူ: {seller_label}\n\n"
        "24 နာရီအတွင်း Seller ထံ ဆုံးဖြတ်ချက်တောင်းခံခဲ့သော်လည်း "
        "တုံ့ပြန်မှု မရရှိသေးပါ။ Admin မှ စစ်ဆေးပေးပါ။"
    )

    post_url = await _post_url(application, book)
    keyboard = None
    if post_url:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📢 Listing Post ကို ကြည့်ရန်", url=post_url)]]
        )

    sent_admin_ids: list[int] = []
    last_error: str | None = None

    for admin_id in admin_ids:
        try:
            await application.bot.send_message(
                chat_id=admin_id,
                text=message,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            sent_admin_ids.append(admin_id)
        except TelegramError as exc:
            last_error = str(exc)
            logger.exception(
                "Could not escalate Pending request %s to admin %s.",
                request.get("_id"),
                admin_id,
            )

    if not sent_admin_ids:
        try:
            await db.purchase_requests.update_one(
                {"_id": request["_id"], "status": "Pending"},
                {
                    "$set": {
                        "admin_escalation_last_attempt_at": now,
                        "admin_escalation_last_error": (last_error or "Delivery failed")[:500],
                    }
                },
            )
            request["admin_escalation_last_attempt_at"] = now
        except PyMongoError:
            logger.exception(
                "Could not save failed Admin escalation attempt for request %s.",
                request.get("_id"),
            )
        return

    try:
        result = await db.purchase_requests.update_one(
            {
                "_id": request["_id"],
                "status": "Pending",
                "admin_escalated_at": {"$exists": False},
            },
            {
                "$set": {
                    "admin_escalated_at": now,
                    "admin_escalated_to": sent_admin_ids,
                },
                "$unset": {
                    "admin_escalation_last_attempt_at": "",
                    "admin_escalation_last_error": "",
                },
            },
        )
    except PyMongoError:
        logger.exception(
            "Admin notification sent but escalation marker failed for request %s.",
            request.get("_id"),
        )
        return

    if result.modified_count == 1:
        request["admin_escalated_at"] = now
        await record_audit_event(
            db,
            event_type="admin_escalation_sent",
            actor_id=None,
            actor_role="system",
            book_id=book.get("_id"),
            request_id=request.get("_id"),
            details={
                "title": str(book.get("title", "Untitled")),
                "admin_ids": sent_admin_ids,
                "age_hours": 48,
            },
        )
        logger.info(
            "Pending request %s escalated to admins %s.",
            request.get("_id"),
            sent_admin_ids,
        )


async def process_pending_lifecycle(application: Application) -> None:
    """Process reminders and escalation for active Pending purchase requests."""

    db = get_database()
    now = datetime.now(timezone.utc)

    cursor = db.purchase_requests.find(
        {
            "status": "Pending",
            "created_at": {"$exists": True},
        }
    )

    async for request in cursor:
        try:
            created_at = request.get("created_at")
            if not isinstance(created_at, datetime):
                logger.warning(
                    "Skipping Pending request %s with invalid created_at.",
                    request.get("_id"),
                )
                continue

            age = now - _as_utc(created_at)
            if age < WARNING_AFTER:
                continue

            book = await _load_active_pending_book(db, request)
            if book is None:
                # Never send reminders/escalation for a request which no longer
                # represents the active buyer on a Pending listing.
                continue

            seller_id = request.get("seller_id")
            if not isinstance(seller_id, int):
                logger.warning(
                    "Skipping lifecycle message for request %s: invalid seller_id.",
                    request.get("_id"),
                )
                continue

            title = escape(str(book.get("title", "Untitled")))
            book_id = str(book.get("_id"))

            # T+22h: a gentle reminder with the seller's existing controls.
            if age >= WARNING_AFTER and not request.get("seller_warning_sent_at"):
                warning_sent = await _send_seller_stage(
                    application=application,
                    db=db,
                    request=request,
                    seller_id=seller_id,
                    text=(
                        "⏰ <b>Pending ဝယ်ယူမှု သတိပေးချက်</b>\n\n"
                        f"📚 စာအုပ်: <b>{title}</b>\n"
                        "ဒီစာအုပ်အတွက် ဝယ်ယူမှု Request ရှိနေသည်မှာ "
                        "22 နာရီခန့် ရှိပါပြီ။\n\n"
                        "ဝယ်သူနဲ့ ဆက်သွယ်ပြီး အခြေအနေကို စစ်ဆေးပေးပါ။ "
                        "ပြီးဆုံးပါက အောက်ပါ Button များမှ Update လုပ်နိုင်ပါတယ်။"
                    ),
                    marker_field="seller_warning_sent_at",
                    attempt_field="seller_warning_last_attempt_at",
                    error_field="seller_warning_last_error",
                    reply_markup=seller_control_keyboard(book_id),
                    audit_title=str(book.get("title", "Untitled")),
                )
                if warning_sent:
                    request["seller_warning_sent_at"] = now

            # T+24h: ask the seller to explicitly continue or release the listing.
            # Seller decision is stored on the purchase request, and is the
            # condition used later to avoid a needless 48-hour escalation.
            if (
                age >= DECISION_AFTER
                and not request.get("seller_decision_requested_at")
                and not request.get("seller_decision")
            ):
                decision_sent = await _send_seller_stage(
                    application=application,
                    db=db,
                    request=request,
                    seller_id=seller_id,
                    text=(
                        "📌 <b>ဝယ်ယူမှု ဆက်လက်လုပ်ဆောင်မလား?</b>\n\n"
                        f"📚 စာအုပ်: <b>{title}</b>\n"
                        "ဒီ Listing ကို Pending အဖြစ် 24 နာရီ ရှိသွားပါပြီ။\n\n"
                        "ဆက်လက်ညှိနှိုင်းမယ်ဆိုရင် ပထမ Button ကိုနှိပ်ပါ။ "
                        "စာအုပ်ကို အခြားသူများ ပြန်ဝယ်နိုင်အောင် ဖွင့်မယ်ဆိုရင် "
                        "ဒုတိယ Button ကိုနှိပ်ပါ။\n\n"
                        "တုံ့ပြန်မှု မရှိပါက 48 နာရီတွင် Admin ထံ အသိပေးပါမယ်။"
                    ),
                    marker_field="seller_decision_requested_at",
                    attempt_field="seller_decision_prompt_last_attempt_at",
                    error_field="seller_decision_prompt_last_error",
                    reply_markup=pending_decision_keyboard(book_id),
                    audit_title=str(book.get("title", "Untitled")),
                )
                if decision_sent:
                    request["seller_decision_requested_at"] = now

            # T+48h: escalate only if the seller has not made a decision.
            if age >= ESCALATION_AFTER and not request.get("seller_decision"):
                await _escalate_to_admins(
                    application=application,
                    db=db,
                    request=request,
                    book=book,
                )

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Pending lifecycle processing failed for request %s.",
                request.get("_id"),
            )


async def pending_lifecycle_loop(application: Application) -> None:
    """Run lifecycle processing periodically until the application shuts down."""

    logger.info(
        "Pending lifecycle monitor active: warning=%sh, decision=%sh, escalation=%sh.",
        int(WARNING_AFTER.total_seconds() // 3600),
        int(DECISION_AFTER.total_seconds() // 3600),
        int(ESCALATION_AFTER.total_seconds() // 3600),
    )

    while True:
        try:
            await process_pending_lifecycle(application)
        except asyncio.CancelledError:
            logger.info("Pending lifecycle monitor stopping.")
            raise
        except Exception:
            logger.exception("Pending lifecycle monitor cycle failed.")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

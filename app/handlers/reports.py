import logging
from datetime import datetime, timezone
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    User,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

from app.config import settings
from app.database.mongo import get_database
from app.keyboards.report import (
    REPORT_REASONS,
    report_reason_keyboard,
)


logger = logging.getLogger(__name__)

# The list is stored in this user's PTB user_data.
# It prevents repeated Report Form DMs for the same book
# while the form is already waiting for a response.
PENDING_REPORT_FORMS_KEY = "pending_report_forms"


def _remove_pending_form(
    user_data: dict,
    book_id: str,
) -> None:
    """Remove a book from the user's pending report forms."""

    pending = user_data.get(PENDING_REPORT_FORMS_KEY, [])

    if not isinstance(pending, list):
        pending = []

    user_data[PENDING_REPORT_FORMS_KEY] = [
        item
        for item in pending
        if item != book_id
    ]


async def open_report_form(
    bot,
    user: User,
    raw_book_id: str,
    user_data: dict,
) -> tuple[str, bool, bool]:
    """
    Open a Report Form in the user's private chat.

    Used by both legacy Channel callback buttons and
    Telegram Deep Links.

    Returns:
        (message, show_alert, form_was_sent)
    """

    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        return (
            "စာအုပ် ID မမှန်ကန်ပါ။",
            True,
            False,
        )

    # Normalize the ID to avoid case inconsistencies.
    raw_book_id = str(book_id)

    db = get_database()

    try:
        registered_user = await db.users.find_one({
            "_id": user.id,
        })

        if registered_user is None:
            return (
                "Report တင်ရန် Bot ကို Start လုပ်ပြီး "
                "ပြန်ကြိုးစားပေးပါ။",
                True,
                False,
            )

        book = await db.books.find_one({
            "_id": book_id,
        })

        if book is None or book.get("admin_hidden"):
            return (
                "ဒီ Listing ကို Report တင်လို့ မရတော့ပါဘူး။",
                True,
                False,
            )

        if book.get("seller_id") == user.id:
            return (
                "ကိုယ့် Listing ကို ကိုယ် Report တင်လို့ "
                "မရပါဘူး။",
                True,
                False,
            )

        existing_report = await db.reports.find_one({
            "reporter_id": user.id,
            "book_id": book_id,
            "status": "Open",
        })

    except PyMongoError:
        logger.exception(
            "Could not prepare report form for user %s, book %s.",
            user.id,
            book_id,
        )

        return (
            "Report Form ဖွင့်ရာမှာ အမှားဖြစ်သွားပါတယ်။ "
            "နောက်တစ်ကြိမ် ပြန်ကြိုးစားပါ။",
            True,
            False,
        )

    if existing_report:
        return (
            "ဒီ Listing အတွက် သင့် Report ကို Admin က "
            "စစ်ဆေးနေဆဲ ဖြစ်ပါတယ်။",
            True,
            False,
        )

    pending = user_data.get(
        PENDING_REPORT_FORMS_KEY,
        [],
    )

    if not isinstance(pending, list):
        pending = []

    # Prevent sending another form when the same user
    # repeatedly opens the same listing's Report link.
    if raw_book_id in pending:
        return (
            "ဒီ Listing အတွက် Report Form ပို့ပြီးပါပြီ။ "
            "Bot Private Chat ထဲက Form ကို အသုံးပြုပေးပါ။",
            False,
            False,
        )

    title = escape(
        str(book.get("title", "Untitled"))
    )

    try:
        await bot.send_message(
            chat_id=user.id,
            text=(
                "🚩 <b>Listing Report</b>\n\n"
                f"စာအုပ်: {title}\n\n"
                "ဒီ Listing ကို ဘာကြောင့် Report တင်လိုတာလဲ "
                "ရွေးချယ်ပေးပါ။\n\n"
                "မမှန်မကန် Report များကို ရှောင်ကြဉ်ပါ။"
            ),
            reply_markup=report_reason_keyboard(
                str(book_id)
            ),
            parse_mode="HTML",
        )

    except TelegramError:
        logger.warning(
            "Could not send report form to user %s.",
            user.id,
            exc_info=True,
        )

        return (
            "Report Form ပို့မရပါ။ Bot ကို Private Chat မှာ "
            "Start လုပ်ထားကြောင်း စစ်ဆေးပေးပါ။",
            True,
            False,
        )

    pending.append(raw_book_id)
    user_data[PENDING_REPORT_FORMS_KEY] = pending

    logger.info(
        "Report form sent to user %s for book %s.",
        user.id,
        book_id,
    )

    return (
        "Report Form ကို Bot Private Chat ဆီ ပို့ပြီးပါပြီ။",
        False,
        True,
    )


async def start_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle existing report callback buttons."""

    query = update.callback_query

    if query is None or query.data is None:
        return

    raw_book_id = query.data.removeprefix(
        "report:book:"
    )

    message, show_alert, _form_was_sent = (
        await open_report_form(
            bot=context.bot,
            user=query.from_user,
            raw_book_id=raw_book_id,
            user_data=context.user_data,
        )
    )

    await query.answer(
        message,
        show_alert=show_alert,
    )


async def _get_user_display_name(
    db,
    telegram_user_id: int | None,
) -> str:
    """Return a username/name without exposing the Telegram numeric ID."""

    if telegram_user_id is None:
        return "မသိရှိပါ"

    try:
        user_doc = await db.users.find_one({"_id": telegram_user_id})
    except PyMongoError:
        logger.exception(
            "Could not look up username for Telegram user %s.",
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
        username = str(username).strip().removeprefix("@")
        if username:
            return f"@{escape(username)}"

    first_name = user_doc.get("first_name") or user_doc.get("name")
    if first_name:
        return escape(str(first_name))

    return "Username မရှိပါ"


async def _get_channel_post_url(
    context: ContextTypes.DEFAULT_TYPE,
    book: dict | None,
) -> str | None:
    """Build a direct URL to the listing post when its location is known."""

    if not book:
        return None

    message_id = book.get("channel_message_id")
    channel_id = book.get("channel_id")

    if not message_id or not channel_id:
        return None

    username = None
    try:
        chat = await context.bot.get_chat(channel_id)
        username = getattr(chat, "username", None)
    except TelegramError:
        logger.info(
            "Could not resolve channel username for book %s.",
            book.get("_id"),
            exc_info=True,
        )

    if not username and isinstance(channel_id, str):
        candidate = channel_id.strip()
        if candidate.startswith("@"):
            username = candidate[1:]

    if username:
        return f"https://t.me/{username}/{int(message_id)}"

    channel_id_text = str(channel_id).strip()
    if channel_id_text.startswith("-100") and channel_id_text[4:].isdigit():
        return (
            f"https://t.me/c/{channel_id_text[4:]}/"
            f"{int(message_id)}"
        )

    return None


async def notify_admins_new_report(
    context: ContextTypes.DEFAULT_TYPE,
    report: dict,
) -> None:
    """Notify configured admins with usernames and a direct listing-post link."""

    admin_ids = settings.admin_telegram_ids

    if not admin_ids:
        logger.warning(
            "Report %s was saved, but ADMIN_IDS is empty.",
            report.get("_id"),
        )
        return

    db = get_database()
    book_id = report.get("book_id")

    try:
        book = await db.books.find_one({"_id": book_id}) if book_id else None
    except PyMongoError:
        logger.exception(
            "Could not look up book for report %s.",
            report.get("_id"),
        )
        book = None

    reporter_name = await _get_user_display_name(
        db,
        report.get("reporter_id"),
    )
    seller_name = await _get_user_display_name(
        db,
        report.get("seller_id"),
    )

    title = escape(
        str(report.get("book_title_snapshot", "Untitled"))
    )
    reason = escape(
        str(report.get("reason_label", "Unknown"))
    )
    book_status = escape(
        str(report.get("book_status_snapshot", "Unknown"))
    )

    notification_text = (
        "🚨 <b>REPORT အသစ် ရောက်ရှိလာပါပြီ</b>\n\n"
        f"📚 စာအုပ်: <b>{title}</b>\n"
        f"📝 အကြောင်းရင်း: {reason}\n"
        f"📌 Listing Status: {book_status}\n"
        f"👤 Reporter: {reporter_name}\n"
        f"👤 Seller: {seller_name}\n\n"
        "မူရင်း Channel Post ကို အောက်က ခလုတ်မှ ဖွင့်ကြည့်နိုင်ပါတယ်။"
    )

    post_url = await _get_channel_post_url(context, book)
    keyboard = None
    if post_url:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 မူရင်း Channel Post ကို ကြည့်ရန်",
                    url=post_url,
                )
            ]
        ])
    else:
        notification_text += (
            "\n\n⚠️ မူရင်း Post Link ကို မထုတ်နိုင်ပါ။ "
            "Listing မှာ channel_id နဲ့ channel_message_id ရှိမရှိ စစ်ဆေးပါ။"
        )

    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            logger.info(
                "New report notification sent to admin %s for book %s.",
                admin_id,
                book_id,
            )
        except TelegramError:
            logger.exception(
                "Could not notify admin %s about report %s.",
                admin_id,
                report.get("_id"),
            )

async def submit_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Save a report after the user selects a reason."""

    query = update.callback_query
    user = update.effective_user

    if query is None or query.data is None or user is None:
        return

    if (
        query.message
        and query.message.chat.type != "private"
    ):
        await query.answer(
            "Report Form ကို Bot Private Chat မှာ အသုံးပြုပါ။",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "Report အချက်အလက် မမှန်ကန်ပါ။",
            show_alert=True,
        )
        return

    raw_book_id = parts[2]
    reason_code = parts[3]

    if reason_code not in REPORT_REASONS:
        await query.answer(
            "Report အကြောင်းရင်း မမှန်ကန်ပါ။",
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

    # Use canonical ObjectId text for pending-form cleanup.
    raw_book_id = str(book_id)

    db = get_database()

    try:
        registered_user = await db.users.find_one({
            "_id": user.id,
        })

        if registered_user is None:
            await query.answer(
                "Bot ကို Start လုပ်ပြီးမှ Report တင်နိုင်ပါတယ်။",
                show_alert=True,
            )
            return

        book = await db.books.find_one({
            "_id": book_id,
        })

        if book is None or book.get("admin_hidden"):
            _remove_pending_form(
                context.user_data,
                raw_book_id,
            )

            await query.answer(
                "ဒီ Listing ကို Report တင်လို့ မရတော့ပါဘူး။",
                show_alert=True,
            )

            await query.edit_message_text(
                "ဒီ Listing ကို Report တင်လို့ မရတော့ပါဘူး။"
            )
            return

        if book.get("seller_id") == user.id:
            _remove_pending_form(
                context.user_data,
                raw_book_id,
            )

            await query.answer(
                "ကိုယ့် Listing ကို ကိုယ် Report တင်လို့ "
                "မရပါဘူး။",
                show_alert=True,
            )

            await query.edit_message_text(
                "ကိုယ့် Listing ကို ကိုယ် Report တင်လို့ "
                "မရပါဘူး။"
            )
            return

        # Check for an existing Open Report before attempting insert.
        existing_report = await db.reports.find_one({
            "reporter_id": user.id,
            "book_id": book_id,
            "status": "Open",
        })

    except PyMongoError:
        logger.exception(
            "Could not validate report from user %s for book %s.",
            user.id,
            book_id,
        )

        await query.answer(
            "Report အချက်အလက် စစ်ဆေးရာမှာ "
            "အမှားဖြစ်သွားပါတယ်။",
            show_alert=True,
        )
        return

    if existing_report:
        _remove_pending_form(
            context.user_data,
            raw_book_id,
        )

        await query.answer(
            "ဒီ Listing အတွက် သင့် Report ကို "
            "စစ်ဆေးနေဆဲ ဖြစ်ပါတယ်။",
            show_alert=True,
        )

        await query.edit_message_text(
            "ဒီ Listing အတွက် သင့် Report ကို "
            "Admin က စစ်ဆေးနေဆဲ ဖြစ်ပါတယ်။"
        )
        return

    now = datetime.now(timezone.utc)

    report = {
        "_id": ObjectId(),
        "book_id": book_id,
        "book_title_snapshot": str(
            book.get("title", "Untitled")
        ),
        "book_status_snapshot": book.get(
            "status",
            "Unknown",
        ),
        "seller_id": book.get("seller_id"),
        "reporter_id": user.id,
        "reason": reason_code,
        "reason_label": REPORT_REASONS[reason_code],
        "status": "Open",
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "resolved_by": None,
    }

    try:
        # The existing partial unique index
        # one_open_report_per_user_book prevents concurrent duplicates.
        await db.reports.insert_one(report)

    except DuplicateKeyError:
        _remove_pending_form(
            context.user_data,
            raw_book_id,
        )

        await query.answer(
            "ဒီ Listing အတွက် သင့် Report ကို "
            "စစ်ဆေးနေဆဲ ဖြစ်ပါတယ်။",
            show_alert=True,
        )

        await query.edit_message_text(
            "ဒီ Listing အတွက် သင့် Report ကို "
            "Admin က စစ်ဆေးနေဆဲ ဖြစ်ပါတယ်။"
        )
        return

    except PyMongoError:
        logger.exception(
            "Failed to save report for book %s from user %s.",
            book_id,
            user.id,
        )

        await query.answer(
            "Report သိမ်းဆည်းရာမှာ အမှားဖြစ်သွားပါတယ်။",
            show_alert=True,
        )

        await query.edit_message_text(
            "Report သိမ်းဆည်းရာမှာ အမှားဖြစ်သွားပါတယ်။ "
            "ခဏနေမှ ပြန်ကြိုးစားပါ။"
        )
        return

    # The report was saved successfully.
    _remove_pending_form(
        context.user_data,
        raw_book_id,
    )

    await query.answer("Report တင်ပြီးပါပြီ။")

    try:
        await query.edit_message_text(
            "✅ <b>Report တင်ပြီးပါပြီ။</b>\n\n"
            f"စာအုပ်: {escape(report['book_title_snapshot'])}\n"
            f"အကြောင်းရင်း: {escape(report['reason_label'])}\n\n"
            "Admin ကို အသိပေးပြီးပါပြီ။\n"
            "Report တင်ခြင်းက Listing ကို အလိုအလျောက် "
            "ဖယ်ရှားတာ မဟုတ်ပါဘူး။",
            parse_mode="HTML",
        )

    except TelegramError:
        logger.exception(
            "Could not update report confirmation for user %s.",
            user.id,
        )

    # Notify Admins only after MongoDB successfully stores the report.
    await notify_admins_new_report(
        context=context,
        report=report,
    )

    logger.info(
        "New report created: report_id=%s book_id=%s "
        "reporter_id=%s reason=%s",
        report["_id"],
        book_id,
        user.id,
        reason_code,
    )



async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    raw_book_id = query.data.removeprefix("report:cancel:")
    _remove_pending_form(context.user_data, raw_book_id)
    await query.answer("Report ပယ်ဖျက်ပြီးပါပြီ။")
    try:
        await query.edit_message_text("Report တင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")
    except TelegramError:
        logger.exception("Could not edit cancelled report form.")


def register_report_handlers(
    application: Application,
) -> None:
    """Register user-facing report callbacks."""

    application.add_handler(
        CallbackQueryHandler(
            start_report,
            pattern=r"^report:book:[0-9a-fA-F]{24}$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            cancel_report,
            pattern=r"^report:cancel:[0-9a-fA-F]{24}$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            submit_report,
            pattern=r"^report:reason:[0-9a-fA-F]{24}:[a-z_]+$",
        )
    )

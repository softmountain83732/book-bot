#app/handlers/admin.py
import logging
from datetime import datetime, timezone
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.config import settings
from app.database.mongo import get_database
from app.keyboards.admin import (
    PAGE_SIZE,
    admin_book_detail_keyboard,
    admin_book_list_keyboard,
    admin_dashboard_keyboard,
    admin_request_detail_keyboard,
    admin_requests_keyboard,
    admin_user_detail_keyboard,
    admin_users_keyboard,
)
from app.services.channel_service import format_semester, update_book_channel


logger = logging.getLogger(__name__)


STATUS_LABELS = {
    "Available": "🟢 ရောင်းရန်ရှိ",
    "Pending": "🟠 ညှိနှိုင်းနေဆဲ",
    "Sold": "✅ ရောင်းထွက်",
    "Cancelled": "⚫ ပယ်ဖျက်ထား",
}

FILTER_TO_STATUS = {
    "available": "Available",
    "pending": "Pending",
    "sold": "Sold",
    "cancelled": "Cancelled",
}


def is_admin(user_id: int | None) -> bool:
    """Return whether a Telegram ID is configured as an administrator."""

    return user_id is not None and user_id in settings.admin_telegram_ids


def format_price(book: dict) -> str:
    if book.get("is_negotiable"):
        return "ဈေးညှိနှိုင်း"

    price = book.get("price")

    if isinstance(price, (int, float)):
        return f"{price:,.0f} MMK"

    return "ဈေးနှုန်း မသတ်မှတ်ထားပါ"


def get_filter_query(filter_slug: str) -> dict:
    """Build a book-status filter."""

    status = FILTER_TO_STATUS.get(filter_slug)

    if status:
        return {"status": status}

    return {}


async def safe_edit(
    query,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Safely edit the current admin message."""

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    except TelegramError as exc:
        if "message is not modified" in str(exc).lower():
            return

        logger.warning("Failed to edit admin message: %s", exc)

        if query.message:
            try:
                await query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            except TelegramError:
                logger.exception("Failed to send fallback admin message.")


async def send_user_notification(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int | None,
    text: str,
) -> bool:
    """Send a notification without failing the whole admin action."""

    if user_id is None:
        return False

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
        )
        return True

    except TelegramError:
        logger.warning(
            "Could not send admin notification to Telegram user %s.",
            user_id,
            exc_info=True,
        )
        return False


async def dashboard_content() -> str:
    """Collect marketplace statistics for the admin dashboard."""

    db = get_database()

    user_count = await db.users.count_documents({})
    book_count = await db.books.count_documents({})

    counts = {}

    for status in ("Available", "Pending", "Sold", "Cancelled"):
        counts[status] = await db.books.count_documents({
            "status": status,
        })

    pending_requests = await db.purchase_requests.count_documents({
        "status": "Pending",
    })

    return (
        "🛡️ <b>Admin Dashboard</b>\n\n"
        "📊 <b>Marketplace Statistics</b>\n\n"
        f"👥 Registered Users: <b>{user_count:,}</b>\n"
        f"📚 စာအုပ်စုစုပေါင်း: <b>{book_count:,}</b>\n\n"
        f"🟢 Available: <b>{counts['Available']:,}</b>\n"
        f"🟠 Pending: <b>{counts['Pending']:,}</b>\n"
        f"✅ Sold: <b>{counts['Sold']:,}</b>\n"
        f"⚫ Cancelled: <b>{counts['Cancelled']:,}</b>\n\n"
        f"🔔 Pending Requests: <b>{pending_requests:,}</b>\n\n"
        "အောက်က Menu မှာ စီမံလိုတဲ့အပိုင်းကို ရွေးချယ်ပါ။"
    )


async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the admin dashboard with /admin."""

    user = update.effective_user
    message = update.effective_message

    if message is None or user is None:
        return

    if not is_admin(user.id):
        await message.reply_text(
            "⛔ Admin ခွင့်ပြုချက် မရှိပါ။"
        )
        return

    try:
        text = await dashboard_content()

        await message.reply_text(
            text,
            reply_markup=admin_dashboard_keyboard(),
            parse_mode="HTML",
        )

    except Exception:
        logger.exception("Failed to load admin dashboard.")

        await message.reply_text(
            "Dashboard ကို ဖွင့်ရာမှာ အမှားဖြစ်သွားပါတယ်။ "
            "Log ကို စစ်ဆေးပါ။"
        )


async def show_dashboard(query) -> None:
    try:
        text = await dashboard_content()

        await safe_edit(
            query,
            text,
            admin_dashboard_keyboard(),
        )

    except Exception:
        logger.exception("Failed to refresh admin dashboard.")

        await safe_edit(
            query,
            "Dashboard ကို Update လုပ်ရာမှာ အမှားဖြစ်သွားပါတယ်။",
            admin_dashboard_keyboard(),
        )


# --------------------------------------------------
# Book listings
# --------------------------------------------------

async def show_admin_books(
    query,
    filter_slug: str,
    offset: int,
) -> None:
    """Show a paginated book listing for moderation."""

    if filter_slug not in ("all", *FILTER_TO_STATUS.keys()):
        filter_slug = "all"

    offset = max(0, offset)

    try:
        db = get_database()
        mongo_query = get_filter_query(filter_slug)

        total = await db.books.count_documents(mongo_query)

        if total > 0 and offset >= total:
            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE

        cursor = (
            db.books.find(mongo_query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(PAGE_SIZE)
        )

        books = []

        async for book in cursor:
            books.append(book)

    except Exception:
        logger.exception("Could not retrieve admin book listings.")

        await safe_edit(
            query,
            "စာအုပ်စာရင်းကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",
            admin_dashboard_keyboard(),
        )
        return

    label = {
        "all": "စာအုပ်အားလုံး",
        "available": "ရောင်းရန်ရှိ",
        "pending": "ညှိနှိုင်းနေဆဲ",
        "sold": "ရောင်းထွက်",
        "cancelled": "ပယ်ဖျက်ထား",
    }.get(filter_slug, "စာအုပ်အားလုံး")

    if not books:
        await safe_edit(
            query,
            f"📚 <b>{label}</b>\n\nဒီအမျိုးအစားမှာ စာအုပ်မရှိပါ။",
            admin_book_list_keyboard(
                books=[],
                filter_slug=filter_slug,
                offset=0,
                total=0,
            ),
        )
        return

    page_number = offset // PAGE_SIZE + 1
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    lines = [
        f"📚 <b>{label}</b>",
        "",
        f"စာအုပ်စုစုပေါင်း: <b>{total:,}</b>",
        f"စာမျက်နှာ: <b>{page_number}/{total_pages}</b>",
        "",
    ]

    for index, book in enumerate(books, start=offset + 1):
        title = escape(str(book.get("title", "Untitled")))
        major = escape(str(book.get("major", "N/A")))
        price = escape(format_price(book))
        status = book.get("status", "Unknown")
        status_text = STATUS_LABELS.get(status, escape(status))
        seller_id = book.get("seller_id", "N/A")

        moderation_mark = (
            "\n🚫 Admin မှ ဖယ်ရှားထားသည်"
            if book.get("admin_hidden")
            else ""
        )

        lines.extend([
            f"<b>{index}. {title}</b>",
            f"🎓 {major} | 💰 {price}",
            f"📌 {status_text} | Seller ID: <code>{seller_id}</code>",
            moderation_mark,
            "",
        ])

    lines.append("အသေးစိတ်စစ်ဆေးရန် စာအုပ်တစ်အုပ်ကို ရွေးပါ။")

    await safe_edit(
        query,
        "\n".join(lines),
        admin_book_list_keyboard(
            books=books,
            filter_slug=filter_slug,
            offset=offset,
            total=total,
        ),
    )


async def show_admin_book_detail(
    query,
    raw_book_id: str,
    filter_slug: str,
    offset: int,
    notice: str | None = None,
) -> None:
    """Show a selected listing, including moderation status."""

    try:
        book_id = ObjectId(raw_book_id)

    except (InvalidId, TypeError):
        await safe_edit(
            query,
            "စာအုပ် ID မမှန်ကန်ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    db = get_database()

    book = await db.books.find_one({"_id": book_id})

    if book is None:
        await safe_edit(
            query,
            "ဒီစာအုပ်ကို ရှာမတွေ့တော့ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    status = book.get("status", "Unknown")
    title = escape(str(book.get("title", "Untitled")))
    major = escape(str(book.get("major", "N/A")))
    year = escape(str(book.get("year", "N/A")))
    semester = escape(format_semester(book.get("year"), book.get("semester", "N/A")))
    condition = escape(str(book.get("condition", "N/A")))
    price = escape(format_price(book))

    seller_id = book.get("seller_id")
    buyer_id = book.get("current_buyer_id")
    channel_message_id = book.get("channel_message_id")

    lines = []

    if notice:
        lines.extend([
            f"ℹ️ {escape(notice)}",
            "",
        ])

    lines.extend([
        "🛡️ <b>Listing Moderation</b>",
        "",
        f"📚 <b>{title}</b>",
        f"🎓 Major: {major}",
        f"📖 Year: {year}",
        f"📑 Semester: {semester}",
        f"💰 ဈေးနှုန်း: {price}",
        f"📝 အခြေအနေ: {condition}",
        f"📌 Status: {STATUS_LABELS.get(status, escape(status))}",
        f"🆔 Book ID: <code>{book_id}</code>",
        f"👤 Seller ID: <code>{seller_id}</code>",
    ])

    if buyer_id is not None:
        lines.append(f"🛒 Buyer ID: <code>{buyer_id}</code>")

    if channel_message_id:
        lines.append(
            f"📣 Channel Message ID: <code>{channel_message_id}</code>"
        )

    if book.get("admin_hidden"):
        lines.extend([
            "",
            "🚫 <b>Admin Moderation:</b> ဖယ်ရှားထားသော Listing ဖြစ်သည်။",
            "Seller က ကိုယ်တိုင် ပြန်လည်ဖော်ပြ၍ မရပါ။",
        ])

        if book.get("admin_cancelled_by") is not None:
            lines.append(
                "Moderated by Admin ID: "
                f"<code>{book['admin_cancelled_by']}</code>"
            )

    await safe_edit(
        query,
        "\n".join(lines),
        admin_book_detail_keyboard(
            book_id=str(book_id),
            status=status,
            filter_slug=filter_slug,
            offset=offset,
            admin_hidden=bool(book.get("admin_hidden")),
        ),
    )


async def cancel_listing_as_admin(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    raw_book_id: str,
    filter_slug: str,
    offset: int,
    admin_id: int,
) -> None:
    """Remove a listing, preventing sellers from reactivating it themselves."""

    try:
        book_id = ObjectId(raw_book_id)

    except (InvalidId, TypeError):
        await safe_edit(
            query,
            "စာအုပ် ID မမှန်ကန်ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    db = get_database()

    book = await db.books.find_one({"_id": book_id})

    if book is None:
        await safe_edit(
            query,
            "ဒီစာအုပ်ကို ရှာမတွေ့တော့ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    if book.get("admin_hidden"):
        await show_admin_book_detail(
            query,
            raw_book_id,
            filter_slug,
            offset,
            notice="ဒီ Listing ကို Admin က ဖယ်ရှားထားပြီးဖြစ်ပါတယ်။",
        )
        return

    old_status = book.get("status")

    if old_status not in ("Available", "Pending"):
        await show_admin_book_detail(
            query,
            raw_book_id,
            filter_slug,
            offset,
            notice="Available သို့မဟုတ် Pending ဖြစ်တဲ့ Listing ကိုသာ ဖယ်ရှားနိုင်ပါတယ်။",
        )
        return

    now = datetime.now(timezone.utc)
    buyer_id = book.get("current_buyer_id")
    seller_id = book.get("seller_id")

    result = await db.books.update_one(
        {
            "_id": book_id,
            "status": old_status,
            "admin_hidden": {"$ne": True},
        },
        {
            "$set": {
                "status": "Cancelled",
                "current_buyer_id": None,
                "updated_at": now,
                "admin_hidden": True,
                "admin_cancelled_by": admin_id,
                "admin_cancelled_at": now,
                "admin_cancelled_from_status": old_status,
            }
        },
    )

    if result.modified_count != 1:
        await show_admin_book_detail(
            query,
            raw_book_id,
            filter_slug,
            offset,
            notice="စာအုပ် Status ပြောင်းလဲသွားပါတယ်။ ပြန်စစ်ပါ။",
        )
        return

    # If a buyer had an active request, close that request too.
    if old_status == "Pending" and buyer_id is not None:
        try:
            await db.purchase_requests.update_one(
                {
                    "book_id": book_id,
                    "buyer_id": buyer_id,
                    "status": "Pending",
                },
                {
                    "$set": {
                        "status": "AdminCancelled",
                        "updated_at": now,
                        "resolution": "admin_cancelled_listing",
                    }
                },
            )

        except Exception:
            logger.exception(
                "Could not update purchase request for moderated book %s",
                book_id,
            )

    book["status"] = "Cancelled"
    book["current_buyer_id"] = None
    book["updated_at"] = now
    book["admin_hidden"] = True
    book["admin_cancelled_by"] = admin_id
    book["admin_cancelled_at"] = now

    channel_ok = True

    try:
        await update_book_channel(
            context.bot,
            book,
            status="Cancelled",
        )

        await db.books.update_one(
            {"_id": book_id},
            {"$unset": {"channel_sync_error": ""}},
        )

    except Exception:
        channel_ok = False

        logger.exception(
            "Failed to update channel after admin removed book %s",
            book_id,
        )

        await db.books.update_one(
            {"_id": book_id},
            {"$set": {"channel_sync_error": True}},
        )

    await send_user_notification(
        context,
        seller_id,
        (
            "⚠️ သင့်စာအုပ် Listing ကို Admin မှ ဖယ်ရှားထားပါတယ်။\n\n"
            f"စာအုပ်: {book.get('title', 'Untitled')}\n"
            "စာအုပ်ကို ကိုယ်တိုင် ပြန်လည်ဖော်ပြလို့ မရပါဘူး။ "
            "လိုအပ်ပါက Marketplace Admin ကို ဆက်သွယ်ပါ။"
        ),
    )

    if old_status == "Pending" and buyer_id is not None:
        await send_user_notification(
            context,
            buyer_id,
            (
                "⚠️ သင်ဝယ်ယူရန် ညှိနှိုင်းနေသော စာအုပ်ကို "
                "Admin မှ ဖယ်ရှားလိုက်ပါတယ်။\n\n"
                f"စာအုပ်: {book.get('title', 'Untitled')}\n"
                "ဒီ Request ကို ပိတ်လိုက်ပါပြီ။"
            ),
        )

    notice = "Listing ကို ဖယ်ရှားပြီး Admin Moderation အဖြစ် မှတ်တမ်းတင်လိုက်ပါပြီ။"

    if channel_ok:
        notice += " Channel Post ကိုလည်း Update လုပ်ပြီးပါပြီ။"
    else:
        notice += " Channel Post ကို Update မလုပ်နိုင်ခဲ့လို့ Bot Log ကို စစ်ဆေးပါ။"

    await show_admin_book_detail(
        query,
        raw_book_id,
        filter_slug,
        offset,
        notice=notice,
    )


async def restore_admin_listing(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    raw_book_id: str,
    filter_slug: str,
    offset: int,
) -> None:
    """Restore a listing previously hidden by an administrator."""

    try:
        book_id = ObjectId(raw_book_id)

    except (InvalidId, TypeError):
        await safe_edit(
            query,
            "စာအုပ် ID မမှန်ကန်ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    db = get_database()

    book = await db.books.find_one({
        "_id": book_id,
        "status": "Cancelled",
        "admin_hidden": True,
    })

    if book is None:
        await show_admin_book_detail(
            query,
            raw_book_id,
            filter_slug,
            offset,
            notice="Admin မှ ဖယ်ရှားထားသော Listing ကို မတွေ့ပါ။",
        )
        return

    now = datetime.now(timezone.utc)

    result = await db.books.update_one(
        {
            "_id": book_id,
            "status": "Cancelled",
            "admin_hidden": True,
        },
        {
            "$set": {
                "status": "Available",
                "current_buyer_id": None,
                "updated_at": now,
            },
            "$unset": {
                "admin_hidden": "",
                "admin_cancelled_by": "",
                "admin_cancelled_at": "",
                "admin_cancelled_from_status": "",
                "channel_sync_error": "",
            },
        },
    )

    if result.modified_count != 1:
        await show_admin_book_detail(
            query,
            raw_book_id,
            filter_slug,
            offset,
            notice="Listing ကို ပြန်လည်ခွင့်ပြုလို့ မရပါ။ Status ကို ပြန်စစ်ပါ။",
        )
        return

    book["status"] = "Available"
    book["current_buyer_id"] = None
    book["updated_at"] = now
    book.pop("admin_hidden", None)

    channel_ok = True

    try:
        await update_book_channel(
            context.bot,
            book,
            status="Available",
        )

        await db.books.update_one(
            {"_id": book_id},
            {"$unset": {"channel_sync_error": ""}},
        )

    except Exception:
        channel_ok = False

        logger.exception(
            "Could not update channel while restoring book %s",
            book_id,
        )

        await db.books.update_one(
            {"_id": book_id},
            {"$set": {"channel_sync_error": True}},
        )

    await send_user_notification(
        context,
        book.get("seller_id"),
        (
            "✅ Admin က သင့်စာအုပ် Listing ကို ပြန်လည်ခွင့်ပြုလိုက်ပါပြီ။\n\n"
            f"စာအုပ်: {book.get('title', 'Untitled')}\n"
            "စာအုပ်ကို Marketplace မှာ ပြန်လည်ရောင်းချနိုင်ပါပြီ။"
        ),
    )

    notice = "Listing ကို ပြန်လည်ခွင့်ပြုပြီး Available ဖြစ်သွားပါပြီ။"

    if channel_ok:
        notice += " Channel Post ကို Update လုပ်ပြီးပါပြီ။"
    else:
        notice += " Channel Post Update မအောင်မြင်လို့ Log ကို စစ်ဆေးပါ။"

    await show_admin_book_detail(
        query,
        raw_book_id,
        filter_slug,
        offset,
        notice=notice,
    )


# --------------------------------------------------
# Registered users
# --------------------------------------------------

async def show_admin_users(
    query,
    offset: int,
) -> None:
    """Show registered users with pagination."""

    offset = max(0, offset)

    try:
        db = get_database()
        total = await db.users.count_documents({})

        if total > 0 and offset >= total:
            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE

        cursor = (
            db.users.find({})
            .sort("created_at", -1)
            .skip(offset)
            .limit(PAGE_SIZE)
        )

        users = []

        async for user in cursor:
            users.append(user)

    except Exception:
        logger.exception("Failed to retrieve registered users.")

        await safe_edit(
            query,
            "User စာရင်းကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",
            admin_dashboard_keyboard(),
        )
        return

    page_number = offset // PAGE_SIZE + 1
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    text_lines = [
        "👥 <b>Registered Users</b>",
        "",
        f"User စုစုပေါင်း: <b>{total:,}</b>",
        f"စာမျက်နှာ: <b>{page_number}/{total_pages}</b>",
        "",
    ]

    for index, user in enumerate(users, start=offset + 1):
        user_id = user.get("_id")
        first_name = escape(str(user.get("first_name") or "No name"))
        username = user.get("username")

        username_text = (
            f" (@{escape(str(username))})"
            if username
            else ""
        )

        text_lines.extend([
            f"<b>{index}. {first_name}</b>{username_text}",
            f"ID: <code>{user_id}</code>",
            "",
        ])

    if not users:
        text_lines.append("User မရှိသေးပါ။")

    await safe_edit(
        query,
        "\n".join(text_lines),
        admin_users_keyboard(
            users=users,
            offset=offset,
            total=total,
        ),
    )


async def show_admin_user_detail(
    query,
    raw_user_id: str,
    offset: int,
) -> None:
    try:
        user_id = int(raw_user_id)

    except (TypeError, ValueError):
        await safe_edit(
            query,
            "User ID မမှန်ကန်ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    db = get_database()
    user = await db.users.find_one({"_id": user_id})

    if user is None:
        await safe_edit(
            query,
            "ဒီ User ကို ရှာမတွေ့တော့ပါ။",
            admin_user_detail_keyboard(offset),
        )
        return

    try:
        book_count = await db.books.count_documents({
            "seller_id": user_id,
        })

        purchase_count = await db.purchase_requests.count_documents({
            "buyer_id": user_id,
        })

    except Exception:
        logger.exception("Could not count user activity.")
        book_count = 0
        purchase_count = 0

    name = escape(str(user.get("first_name") or "No name"))
    last_name = user.get("last_name")

    if last_name:
        name += " " + escape(str(last_name))

    username = user.get("username")
    username_text = (
        f"@{escape(str(username))}"
        if username
        else "မရှိ"
    )

    created_at = user.get("created_at")
    created_text = (
        created_at.strftime("%Y-%m-%d %H:%M UTC")
        if isinstance(created_at, datetime)
        else "မသိရှိပါ"
    )

    text = (
        "👤 <b>User Details</b>\n\n"
        f"အမည်: {name}\n"
        f"Username: {username_text}\n"
        f"Telegram ID: <code>{user_id}</code>\n"
        f"Role: {escape(str(user.get('role', 'user')))}\n"
        f"Register Date: {created_text}\n\n"
        f"📚 တင်ထားသောစာအုပ်: <b>{book_count:,}</b>\n"
        f"🛒 Buyer Requests: <b>{purchase_count:,}</b>"
    )

    await safe_edit(
        query,
        text,
        admin_user_detail_keyboard(offset),
    )


# --------------------------------------------------
# Purchase requests
# --------------------------------------------------

async def show_admin_requests(
    query,
    filter_slug: str,
    offset: int,
) -> None:
    """Show purchase request history or pending requests."""

    if filter_slug not in ("all", "pending"):
        filter_slug = "all"

    offset = max(0, offset)

    mongo_query = (
        {"status": "Pending"}
        if filter_slug == "pending"
        else {}
    )

    try:
        db = get_database()

        total = await db.purchase_requests.count_documents(
            mongo_query
        )

        if total > 0 and offset >= total:
            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE

        cursor = (
            db.purchase_requests.find(mongo_query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(PAGE_SIZE)
        )

        requests = []

        async for request in cursor:
            requests.append(request)

    except Exception:
        logger.exception("Failed to retrieve purchase requests.")

        await safe_edit(
            query,
            "Purchase Request စာရင်းကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",
            admin_dashboard_keyboard(),
        )
        return

    label = (
        "Pending Transactions"
        if filter_slug == "pending"
        else "Purchase Request History"
    )

    page_number = offset // PAGE_SIZE + 1
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    lines = [
        f"📜 <b>{label}</b>",
        "",
        f"Request စုစုပေါင်း: <b>{total:,}</b>",
        f"စာမျက်နှာ: <b>{page_number}/{total_pages}</b>",
        "",
    ]

    for index, request in enumerate(requests, start=offset + 1):
        request_id = escape(str(request.get("_id", "")))
        status = escape(str(request.get("status", "Unknown")))
        buyer_id = request.get("buyer_id", "N/A")
        seller_id = request.get("seller_id", "N/A")
        book_id = request.get("book_id")

        book_title = "စာအုပ် မတွေ့ပါ"

        if isinstance(book_id, ObjectId):
            book = await db.books.find_one(
                {"_id": book_id},
                {"title": 1},
            )

            if book:
                book_title = str(book.get("title", "Untitled"))

        lines.extend([
            f"<b>{index}. {escape(book_title)}</b>",
            f"Status: {status}",
            f"Buyer: <code>{buyer_id}</code>",
            f"Seller: <code>{seller_id}</code>",
            f"Request ID: <code>{request_id[-8:]}</code>",
            "",
        ])

    if not requests:
        lines.append("ဒီအမျိုးအစားမှာ Request မရှိပါ။")

    await safe_edit(
        query,
        "\n".join(lines),
        admin_requests_keyboard(
            requests=requests,
            filter_slug=filter_slug,
            offset=offset,
            total=total,
        ),
    )


async def show_admin_request_detail(
    query,
    raw_request_id: str,
    filter_slug: str,
    offset: int,
) -> None:
    try:
        request_id = ObjectId(raw_request_id)

    except (InvalidId, TypeError):
        await safe_edit(
            query,
            "Request ID မမှန်ကန်ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    db = get_database()

    request = await db.purchase_requests.find_one({
        "_id": request_id,
    })

    if request is None:
        await safe_edit(
            query,
            "ဒီ Request ကို ရှာမတွေ့တော့ပါ။",
            admin_dashboard_keyboard(),
        )
        return

    book_id = request.get("book_id")
    book = None

    if isinstance(book_id, ObjectId):
        book = await db.books.find_one({"_id": book_id})

    buyer_id = request.get("buyer_id")
    seller_id = request.get("seller_id")

    buyer = await db.users.find_one({"_id": buyer_id})
    seller = await db.users.find_one({"_id": seller_id})

    book_title = (
        escape(str(book.get("title", "Untitled")))
        if book
        else "စာအုပ် မတွေ့ပါ"
    )

    def account_text(user_record, telegram_id) -> str:
        if user_record is None:
            return f"ID <code>{telegram_id}</code>"

        name = escape(
            str(user_record.get("first_name") or "No name")
        )

        username = user_record.get("username")

        if username:
            return f"{name} (@{escape(str(username))})"

        return f"{name} — ID <code>{telegram_id}</code>"

    created_at = request.get("created_at")
    created_text = (
        created_at.strftime("%Y-%m-%d %H:%M UTC")
        if isinstance(created_at, datetime)
        else "မသိရှိပါ"
    )

    text = (
        "📜 <b>Purchase Request Details</b>\n\n"
        f"📚 စာအုပ်: {book_title}\n"
        f"🆔 Request ID: <code>{request_id}</code>\n"
        f"📌 Status: {escape(str(request.get('status', 'Unknown')))}\n"
        f"👤 Buyer: {account_text(buyer, buyer_id)}\n"
        f"👤 Seller: {account_text(seller, seller_id)}\n"
        f"🕒 Created: {created_text}"
    )

    if book:
        text += (
            f"\nBook Status: "
            f"{STATUS_LABELS.get(book.get('status'), 'Unknown')}"
        )

    await safe_edit(
        query,
        text,
        admin_request_detail_keyboard(
            filter_slug=filter_slug,
            offset=offset,
        ),
    )


# --------------------------------------------------
# Admin callback router
# --------------------------------------------------

async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user

    if query is None or query.data is None or user is None:
        return

    if not is_admin(user.id):
        await query.answer(
            "⛔ Admin ခွင့်ပြုချက် မရှိပါ။",
            show_alert=True,
        )
        return

    await query.answer()

    data = query.data
    parts = data.split(":")

    try:
        if data == "admin:dashboard":
            await show_dashboard(query)
            return

        if len(parts) == 4 and parts[:2] == ["admin", "books"]:
            filter_slug = parts[2]

            try:
                offset = int(parts[3])
            except ValueError:
                offset = 0

            await show_admin_books(
                query,
                filter_slug,
                max(0, offset),
            )
            return

        if len(parts) == 5 and parts[:2] == ["admin", "book"]:
            raw_book_id = parts[2]
            filter_slug = parts[3]

            try:
                offset = int(parts[4])
            except ValueError:
                offset = 0

            await show_admin_book_detail(
                query,
                raw_book_id,
                filter_slug,
                max(0, offset),
            )
            return

        if len(parts) == 5 and parts[:2] == ["admin", "cancel"]:
            await cancel_listing_as_admin(
                query,
                context,
                raw_book_id=parts[2],
                filter_slug=parts[3],
                offset=max(0, int(parts[4])),
                admin_id=user.id,
            )
            return

        if len(parts) == 5 and parts[:2] == ["admin", "restore"]:
            await restore_admin_listing(
                query,
                context,
                raw_book_id=parts[2],
                filter_slug=parts[3],
                offset=max(0, int(parts[4])),
            )
            return

        if len(parts) == 3 and parts[:2] == ["admin", "users"]:
            try:
                offset = int(parts[2])
            except ValueError:
                offset = 0

            await show_admin_users(
                query,
                max(0, offset),
            )
            return

        if len(parts) == 4 and parts[:2] == ["admin", "user"]:
            await show_admin_user_detail(
                query,
                raw_user_id=parts[2],
                offset=max(0, int(parts[3])),
            )
            return

        if len(parts) == 4 and parts[:2] == ["admin", "requests"]:
            filter_slug = parts[2]

            try:
                offset = int(parts[3])
            except ValueError:
                offset = 0

            await show_admin_requests(
                query,
                filter_slug,
                max(0, offset),
            )
            return

        if len(parts) == 5 and parts[:2] == ["admin", "request"]:
            raw_request_id = parts[2]
            filter_slug = parts[3]

            try:
                offset = int(parts[4])
            except ValueError:
                offset = 0

            await show_admin_request_detail(
                query,
                raw_request_id,
                filter_slug,
                max(0, offset),
            )
            return

        await safe_edit(
            query,
            "Admin action ကို မသိရှိပါ။ Dashboard ကို ပြန်ဖွင့်ပါ။",
            admin_dashboard_keyboard(),
        )

    except Exception:
        logger.exception(
            "Admin action failed for Telegram user %s",
            user.id,
        )

        await safe_edit(
            query,
            "လုပ်ဆောင်မှုမှာ အမှားဖြစ်သွားပါတယ်။ "
            "Bot Log ကို စစ်ဆေးပါ။",
            admin_dashboard_keyboard(),
        )



async def migrate_year2_semesters_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Migrate legacy Year 2 semesters and refresh existing channel captions.

    Safe to run more than once: database values are changed only when they
    still use the old labels; every Year 2 channel post is refreshed so a
    previous Telegram edit failure can be retried.
    """
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⛔ Admin ခွင့်ပြုချက် မရှိပါ။")
        return

    db = get_database()
    migrated_count = 0
    synced_count = 0
    sync_failed_count = 0
    legacy_map = {
        "1": 3,
        "2": 4,
        "both": "3 & 4",
        "1&2": "3 & 4",
        "1 & 2": "3 & 4",
    }

    try:
        cursor = db.books.find({"year": {"$in": [2, "2"]}})
        async for book in cursor:
            old_semester = book.get("semester")
            old_key = str(old_semester).strip().lower().replace("(နှစ်ခုလုံး)", "").strip()
            new_semester = legacy_map.get(old_key)

            if new_semester is not None and new_semester != old_semester:
                result = await db.books.update_one(
                    {"_id": book["_id"], "semester": old_semester},
                    {"$set": {
                        "semester": new_semester,
                        "updated_at": datetime.now(timezone.utc),
                    }},
                )
                if result.modified_count:
                    migrated_count += 1
                    book["semester"] = new_semester
                else:
                    # A concurrent update may have changed the document. Sync
                    # the latest value instead of publishing stale data.
                    latest = await db.books.find_one({"_id": book["_id"]})
                    if latest is not None:
                        book = latest

            if book.get("channel_message_id") and book.get("channel_id"):
                try:
                    await update_book_channel(context.bot, book)
                    synced_count += 1
                except Exception:
                    sync_failed_count += 1
                    logger.exception(
                        "Could not refresh Year 2 channel post for book %s",
                        book.get("_id"),
                    )

    except Exception:
        logger.exception("Year 2 semester migration failed for admin %s", user.id)
        await message.reply_text(
            "Year 2 Semester Migration မှာ အမှားဖြစ်သွားပါတယ်။ Bot Log ကို စစ်ဆေးပါ။\n"
            f"Database ပြောင်းပြီးသား: {migrated_count} ခု\n"
            f"Channel Update အောင်မြင်: {synced_count} ခု\n"
            f"Channel Update မအောင်မြင်: {sync_failed_count} ခု"
        )
        return

    await message.reply_text(
        "✅ Year 2 Semester Migration ပြီးပါပြီ။\n\n"
        f"Database ပြောင်းလဲမှု: {migrated_count} ခု\n"
        f"Channel Post Update အောင်မြင်: {synced_count} ခု\n"
        f"Channel Post Update မအောင်မြင်: {sync_failed_count} ခု\n\n"
        "မအောင်မြင်တဲ့ Channel Post တွေရှိရင် Permission နဲ့ Message ID ကို စစ်ပြီး ဒီ Command ကို ပြန် run နိုင်ပါတယ်။"
    )

def register_admin_handlers(application: Application) -> None:
    """Register the admin command and protected callbacks."""

    application.add_handler(
        CommandHandler("admin", admin_command)
    )

    application.add_handler(
        CommandHandler("migrate_year2_semesters", migrate_year2_semesters_command)
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin:",
        )
    )
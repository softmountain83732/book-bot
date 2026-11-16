import logging
from datetime import datetime, timedelta, timezone
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.config import settings
from app.database.mongo import get_database
from app.services.audit_service import record_audit_event
from app.services.channel_service import update_book_channel


logger = logging.getLogger(__name__)
PAGE_SIZE = 5


def is_admin(user_id: int | None) -> bool:
    """Check admin status using configured Telegram user IDs."""
    if user_id is None:
        return False
    try:
        return any(int(admin_id) == int(user_id) for admin_id in settings.admin_telegram_ids)
    except (TypeError, ValueError):
        return False


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_text(value) -> str:
    if not isinstance(value, datetime):
        return "အချိန်မသိရှိပါ"
    delta = datetime.now(timezone.utc) - _as_utc(value)
    seconds = max(0, int(delta.total_seconds()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days} ရက် {hours} နာရီ"
    if hours:
        return f"{hours} နာရီ {minutes} မိနစ်"
    return f"{minutes} မိနစ်"


def _date_text(value) -> str:
    if not isinstance(value, datetime):
        return "မသိရှိပါ"
    dt = _as_utc(value).astimezone(timezone(timedelta(hours=6, minutes=30)))
    return dt.strftime("%Y-%m-%d %H:%M (MMT)")


async def _user_html_label(db, user_id: int | None) -> str:
    """Return an HTML-linked Telegram user label without showing numeric IDs."""
    if user_id is None:
        return "မသိရှိပါ"

    try:
        record = await db.users.find_one({"_id": user_id})
    except PyMongoError:
        logger.exception("Could not resolve admin queue user label for %s", user_id)
        record = None

    if record:
        username = (
            record.get("username")
            or record.get("telegram_username")
            or record.get("user_name")
        )
        if username:
            label = "@" + str(username).strip().removeprefix("@")
        else:
            label = (
                record.get("first_name")
                or record.get("name")
                or "Telegram user"
            )
    else:
        label = "Telegram user"

    label = escape(str(label))
    return f'<a href="tg://user?id={int(user_id)}">{label}</a>'


async def _post_url(application: Application, book: dict) -> str | None:
    channel_id = book.get("channel_id")
    message_id = book.get("channel_message_id")
    if not channel_id or not message_id:
        return None

    username = None
    try:
        chat = await application.bot.get_chat(channel_id)
        username = getattr(chat, "username", None)
    except TelegramError:
        logger.debug("Could not resolve channel username for book %s", book.get("_id"), exc_info=True)

    if not username and isinstance(channel_id, str) and channel_id.strip().startswith("@"):
        username = channel_id.strip()[1:]

    if username:
        return f"https://t.me/{username}/{int(message_id)}"

    text_id = str(channel_id).strip()
    if text_id.startswith("-100") and text_id[4:].isdigit():
        return f"https://t.me/c/{text_id[4:]}/{int(message_id)}"
    return None


async def _get_active_pending(db, request_id: ObjectId) -> tuple[dict, dict] | None:
    request = await db.purchase_requests.find_one({"_id": request_id, "status": "Pending"})
    if not request:
        return None

    book_id = request.get("book_id")
    if not isinstance(book_id, ObjectId):
        return None
    book = await db.books.find_one({"_id": book_id})
    if not book:
        return None

    if (
        book.get("status") != "Pending"
        or book.get("current_buyer_id") != request.get("buyer_id")
        or book.get("seller_id") != request.get("seller_id")
    ):
        return None
    return request, book


async def _list_active_pending(db) -> list[tuple[dict, dict]]:
    items: list[tuple[dict, dict]] = []
    cursor = db.purchase_requests.find(
        {"status": "Pending", "created_at": {"$exists": True}}
    ).sort("created_at", 1)
    async for request in cursor:
        book_id = request.get("book_id")
        if not isinstance(book_id, ObjectId):
            continue
        try:
            book = await db.books.find_one({"_id": book_id})
        except PyMongoError:
            logger.exception("Could not load pending book %s", book_id)
            continue
        if not book:
            continue
        if (
            book.get("status") == "Pending"
            and book.get("current_buyer_id") == request.get("buyer_id")
            and book.get("seller_id") == request.get("seller_id")
        ):
            items.append((request, book))
    return items


def _queue_keyboard(items: list[tuple[dict, dict]], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    start = page * PAGE_SIZE
    for request, book in items[start:start + PAGE_SIZE]:
        title = str(book.get("title", "Untitled"))
        title = title if len(title) <= 32 else title[:29] + "..."
        age = _age_text(request.get("created_at"))
        rows.append([InlineKeyboardButton(
            f"📚 {title} · {age}",
            callback_data=f"adminpending:detail:{request['_id']}:{page}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ ယခင်", callback_data=f"adminpending:list:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("နောက်တစ်မျက်နှာ ➡️", callback_data=f"adminpending:list:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"adminpending:list:{page}")])
    return InlineKeyboardMarkup(rows)


async def _render_queue(target, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    db = get_database()
    active = await _list_active_pending(db)
    total = len(active)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    if not active:
        text = (
            "🗂️ <b>Pending Purchase Queue</b>\n\n"
            "လက်ရှိ စစ်ဆေးရန် Pending ဝယ်ယူမှု မရှိပါ။"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="adminpending:list:0")]
        ])
    else:
        text = (
            "🗂️ <b>Pending Purchase Queue</b>\n\n"
            f"လက်ရှိ Pending ဝယ်ယူမှု: <b>{total}</b> ခု\n"
            "စာအုပ်တစ်ခုကို ရွေးပြီး အသေးစိတ်နဲ့ ဆုံးဖြတ်ချက်တွေကို ကြည့်ပါ။\n\n"
            "အချိန်အကြာဆုံး Pending ဖြစ်နေတဲ့ Request တွေကို အရင်ပြထားပါတယ်။"
        )
        markup = _queue_keyboard(active, page, total_pages)

    edit_method = getattr(target, "edit_message_text", None)
    if callable(edit_method):
        try:
            await edit_method(text, reply_markup=markup, parse_mode="HTML")
        except TelegramError:
            message = getattr(target, "message", None)
            if message is None:
                raise
            await message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def _render_detail(query, context: ContextTypes.DEFAULT_TYPE, raw_request_id: str, page: int) -> None:
    try:
        request_id = ObjectId(raw_request_id)
    except (InvalidId, TypeError):
        await query.edit_message_text("Request အချက်အလက် မမှန်ကန်ပါ။")
        return

    db = get_database()
    active = await _get_active_pending(db, request_id)
    if not active:
        await query.edit_message_text(
            "ဒီ Request က လက်ရှိ Active Pending မဟုတ်တော့ပါဘူး။\n\n"
            "Queue ကို Refresh လုပ်ပြီး ပြန်စစ်ပါ။",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Pending Queue", callback_data=f"adminpending:list:{max(page, 0)}")]
            ]),
        )
        return

    request, book = active
    seller_label = await _user_html_label(db, request.get("seller_id"))
    buyer_label = await _user_html_label(db, request.get("buyer_id"))
    title = escape(str(book.get("title", "Untitled")))
    decision = request.get("seller_decision")
    if decision == "Continue":
        decision_text = "✅ ဆက်လက်ညှိနှိုင်းမည်ဟု အတည်ပြုပြီး"
    elif decision:
        decision_text = escape(str(decision))
    else:
        decision_text = "⚠️ ဆုံးဖြတ်ချက် မပေးရသေးပါ"

    escalation = _date_text(request.get("admin_escalated_at")) if request.get("admin_escalated_at") else "မပို့ရသေးပါ"
    reviewed = _date_text(request.get("admin_reviewed_at")) if request.get("admin_reviewed_at") else "မစစ်ဆေးရသေးပါ"
    created = _date_text(request.get("created_at"))

    text = (
        "📋 <b>Pending Purchase အသေးစိတ်</b>\n\n"
        f"📚 စာအုပ်: <b>{title}</b>\n"
        f"📌 Listing Status: <b>{escape(str(book.get('status', 'Unknown')))}</b>\n"
        f"👤 ရောင်းသူ: {seller_label}\n"
        f"🛒 ဝယ်သူ: {buyer_label}\n"
        f"🕓 စတင်ချိန်: {created}\n"
        f"⏳ Pending ကြာချိန်: <b>{_age_text(request.get('created_at'))}</b>\n"
        f"🧭 Seller ဆုံးဖြတ်ချက်: {decision_text}\n"
        f"🚨 Admin သို့ Escalate: {escalation}\n"
        f"🔎 Admin နောက်ဆုံးစစ်ဆေးမှု: {reviewed}\n\n"
        "ပြန်ဖွင့်ခြင်း သို့မဟုတ် Sold အဖြစ် ပြောင်းခြင်းမပြုမီ အရောင်းအဝယ်အခြေအနေကို အတည်ပြုပါ။"
    )

    rows = []
    post_url = await _post_url(context.application, book)
    if post_url:
        rows.append([InlineKeyboardButton("📢 မူရင်း Channel Post", url=post_url)])
    seller_id = request.get("seller_id")
    buyer_id = request.get("buyer_id")
    contact_row = []
    if isinstance(seller_id, int):
        contact_row.append(InlineKeyboardButton("👤 Seller Chat", url=f"tg://user?id={seller_id}"))
    if isinstance(buyer_id, int):
        contact_row.append(InlineKeyboardButton("🛒 Buyer Chat", url=f"tg://user?id={buyer_id}"))
    if contact_row:
        rows.append(contact_row)
    rows.append([InlineKeyboardButton("🕓 Pending အဖြစ် ဆက်ထားမည်", callback_data=f"adminpending:keep:{request_id}:{page}")])
    rows.append([InlineKeyboardButton("↩️ Listing ပြန်ဖွင့်ရန် (Review လိုအပ်)", callback_data=f"adminpending:confirmrelease:{request_id}:{page}")])
    rows.append([InlineKeyboardButton("✅ Sold အဖြစ် သတ်မှတ်ရန် (Review လိုအပ်)", callback_data=f"adminpending:confirmsold:{request_id}:{page}")])
    rows.append([InlineKeyboardButton("⬅️ Pending Queue", callback_data=f"adminpending:list:{page}")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML", disable_web_page_preview=True)


async def _confirm_resolution(query, raw_request_id: str, page: int, resolution: str) -> None:
    try:
        request_id = ObjectId(raw_request_id)
    except (InvalidId, TypeError):
        await query.edit_message_text("Request အချက်အလက် မမှန်ကန်ပါ။")
        return
    title = "Listing ပြန်ဖွင့်ခြင်း" if resolution == "release" else "Sold အဖြစ် သတ်မှတ်ခြင်း"
    action = "release" if resolution == "release" else "sold"
    text = (
        f"⚠️ <b>{title} ကို အတည်ပြုပါ</b>\n\n"
        "ဒီလုပ်ဆောင်ချက်က Pending Request ကို ပိတ်ပြီး Listing အခြေအနေကို ပြောင်းလဲပါမယ်။\n"
        "Seller/Buyer နဲ့ အခြေအနေကို စစ်ဆေးပြီးမှ အတည်ပြုပါ။"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ အတည်ပြုမည်", callback_data=f"adminpending:{action}:{request_id}:{page}")],
        [InlineKeyboardButton("❌ မလုပ်တော့ပါ", callback_data=f"adminpending:detail:{request_id}:{page}")],
    ])
    await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")


async def _resolve_request(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    request_id: ObjectId,
    page: int,
    resolution: str,
    admin_id: int,
) -> None:
    db = get_database()
    active = await _get_active_pending(db, request_id)
    if not active:
        await query.edit_message_text(
            "ဒီ Request က Active Pending မဟုတ်တော့ပါဘူး။ Queue ကို Refresh လုပ်ပါ.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Pending Queue", callback_data=f"adminpending:list:{page}")]
            ]),
        )
        return

    request, book = active
    now = datetime.now(timezone.utc)
    buyer_id = request.get("buyer_id")
    new_book_status = "Available" if resolution == "release" else "Sold"
    request_status = "ReleasedByAdmin" if resolution == "release" else "Sold"

    update_fields = {
        "status": new_book_status,
        "updated_at": now,
        "admin_resolution": resolution,
        "admin_resolved_at": now,
        "admin_resolved_by": admin_id,
    }
    if resolution == "release":
        update_fields["current_buyer_id"] = None

    try:
        result = await db.books.update_one(
            {
                "_id": book["_id"],
                "status": "Pending",
                "current_buyer_id": buyer_id,
                "seller_id": request.get("seller_id"),
            },
            {"$set": update_fields},
        )
    except PyMongoError:
        logger.exception("Admin %s could not resolve Pending book %s", admin_id, book.get("_id"))
        await query.edit_message_text("စာအုပ်အခြေအနေ ပြောင်းလဲရာမှာ အမှားဖြစ်သွားပါတယ်။ Log ကို စစ်ဆေးပါ။")
        return

    if result.modified_count != 1:
        await query.edit_message_text("အခြားလုပ်ဆောင်ချက်တစ်ခုကြောင့် Listing အခြေအနေ ပြောင်းလဲသွားပါပြီ။ Queue ကို Refresh လုပ်ပါ။")
        return

    try:
        await db.purchase_requests.update_one(
            {"_id": request_id, "status": "Pending"},
            {"$set": {
                "status": request_status,
                "updated_at": now,
                "admin_resolution": resolution,
                "admin_resolved_at": now,
                "admin_resolved_by": admin_id,
                "admin_reviewed_at": now,
                "admin_reviewed_by": admin_id,
            }},
        )
    except PyMongoError:
        logger.exception("Book was resolved, but request history update failed for %s", request_id)

    await record_audit_event(
        db,
        event_type=("admin_release_listing" if resolution == "release" else "admin_mark_sold"),
        actor_id=admin_id,
        actor_role="admin",
        book_id=book.get("_id"),
        request_id=request_id,
        details={
            "title": str(book.get("title", "Untitled")),
            "resolution": resolution,
            "from_status": "Pending",
            "to_status": new_book_status,
            "request_status": request_status,
        },
    )

    book.update(update_fields)
    try:
        await update_book_channel(context.bot, book, status=new_book_status)
        await db.books.update_one({"_id": book["_id"]}, {"$unset": {"channel_sync_error": ""}})
    except Exception:
        logger.exception("Could not sync Channel post after admin resolution for book %s", book.get("_id"))
        try:
            await db.books.update_one({"_id": book["_id"]}, {"$set": {"channel_sync_error": True}})
        except PyMongoError:
            logger.exception("Could not save channel sync error for book %s", book.get("_id"))

    if resolution == "release":
        buyer_text = "Admin က အခြေအနေကို စစ်ဆေးပြီး ဒီဝယ်ယူမှု Request ကို ပိတ်ကာ Listing ကို ပြန်ဖွင့်လိုက်ပါတယ်။"
        seller_text = "Admin က Pending ဝယ်ယူမှုကို စစ်ဆေးပြီး Listing ကို Available အဖြစ် ပြန်ဖွင့်လိုက်ပါတယ်။"
        admin_text = "✅ Listing ကို Admin ဆုံးဖြတ်ချက်ဖြင့် Available ပြန်ဖွင့်ပြီးပါပြီ။"
    else:
        buyer_text = "Admin က အရောင်းအဝယ်ပြီးဆုံးကြောင်း အတည်ပြုပြီး ဒီစာအုပ်ကို Sold အဖြစ် မှတ်တမ်းတင်လိုက်ပါတယ်။"
        seller_text = "Admin က အရောင်းအဝယ်ပြီးဆုံးကြောင်း အတည်ပြုပြီး စာအုပ်ကို Sold အဖြစ် မှတ်တမ်းတင်လိုက်ပါတယ်။"
        admin_text = "✅ Listing ကို Admin ဆုံးဖြတ်ချက်ဖြင့် Sold အဖြစ် မှတ်တမ်းတင်ပြီးပါပြီ။"

    for person_id, message in ((buyer_id, buyer_text), (request.get("seller_id"), seller_text)):
        if not isinstance(person_id, int):
            continue
        try:
            await context.bot.send_message(chat_id=person_id, text=message)
        except TelegramError:
            logger.warning("Could not notify user %s about admin resolution of book %s", person_id, book.get("_id"), exc_info=True)

    await query.edit_message_text(
        f"{admin_text}\n\n📚 စာအုပ်: <b>{escape(str(book.get('title', 'Untitled')))}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Pending Queue", callback_data=f"adminpending:list:{page}")],
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"adminpending:list:{page}")],
        ]),
    )
    logger.info("Admin %s resolved request %s as %s", admin_id, request_id, resolution)


async def admin_pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if message is None:
        return
    if not is_admin(user.id if user else None):
        await message.reply_text("⛔ ဒီ command ကို Admin များသာ အသုံးပြုနိုင်ပါတယ်။")
        return
    try:
        await _render_queue(message, context, page=0)
    except PyMongoError:
        logger.exception("Could not load Admin Pending Queue")
        await message.reply_text("Pending Queue ကို ဖတ်ရာမှာ အမှားဖြစ်သွားပါတယ်။ Bot Log ကို စစ်ပါ။")


async def admin_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or not query.data or user is None:
        return
    if not is_admin(user.id):
        await query.answer("⛔ Admin ခွင့်ပြုချက် မရှိပါ။", show_alert=True)
        return

    await query.answer()
    parts = query.data.split(":")
    try:
        if len(parts) == 3 and parts[:2] == ["adminpending", "list"]:
            try:
                page = max(0, int(parts[2]))
            except ValueError:
                page = 0
            await _render_queue(query, context, page)
            return

        if len(parts) == 4 and parts[:2] == ["adminpending", "detail"]:
            try:
                page = max(0, int(parts[3]))
            except ValueError:
                page = 0
            await _render_detail(query, context, parts[2], page)
            return

        if len(parts) == 4 and parts[0] == "adminpending":
            action, raw_request_id = parts[1], parts[2]
            try:
                page = max(0, int(parts[3]))
            except ValueError:
                page = 0

            if action == "keep":
                try:
                    request_id = ObjectId(raw_request_id)
                    active = await _get_active_pending(get_database(), request_id)
                    if not active:
                        await query.edit_message_text("ဒီ Request က Active Pending မဟုတ်တော့ပါဘူး။ Queue ကို Refresh လုပ်ပါ။")
                        return
                    now = datetime.now(timezone.utc)
                    db = get_database()
                    current_request = await db.purchase_requests.find_one(
                        {"_id": request_id, "status": "Pending"}
                    )
                    await db.purchase_requests.update_one(
                        {"_id": request_id, "status": "Pending"},
                        {"$set": {
                            "admin_reviewed_at": now,
                            "admin_reviewed_by": user.id,
                            "admin_review_action": "KeptPending",
                        }},
                    )
                    if current_request:
                        book = await db.books.find_one({"_id": current_request.get("book_id")})
                        await record_audit_event(
                            db,
                            event_type="admin_keep_pending",
                            actor_id=user.id,
                            actor_role="admin",
                            book_id=(current_request.get("book_id") if isinstance(current_request.get("book_id"), ObjectId) else None),
                            request_id=request_id,
                            details={
                                "title": str((book or {}).get("title", "Untitled")),
                                "from_status": "Pending",
                                "to_status": "Pending",
                            },
                        )
                    await query.edit_message_text(
                        "🕓 ဒီ Request ကို Admin က စစ်ဆေးပြီး Pending အဖြစ် ဆက်ထားလိုက်ပါတယ်။\n\n"
                        "Seller အတည်ပြုချက် မရှိဘဲ Listing ကို ပြန်မဖွင့်ပါ။",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⬅️ Pending Queue", callback_data=f"adminpending:list:{page}")]
                        ]),
                    )
                except (InvalidId, PyMongoError):
                    logger.exception("Could not mark Pending request as reviewed")
                    await query.edit_message_text("Admin review ကို မှတ်တမ်းတင်ရာမှာ အမှားဖြစ်သွားပါတယ်။")
                return

            if action in ("confirmrelease", "confirmsold"):
                await _confirm_resolution(query, raw_request_id, page, "release" if action == "confirmrelease" else "sold")
                return

            if action in ("release", "sold"):
                try:
                    request_id = ObjectId(raw_request_id)
                except (InvalidId, TypeError):
                    await query.edit_message_text("Request ID မမှန်ကန်ပါ။")
                    return
                await _resolve_request(query, context, request_id, page, action, user.id)
                return

        await query.edit_message_text("Admin Pending action မမှန်ကန်ပါ။")
    except Exception:
        logger.exception("Admin Pending action failed for user %s", user.id)
        try:
            await query.edit_message_text("Pending Request ကို ကိုင်တွယ်ရာမှာ အမှားဖြစ်သွားပါတယ်။ Bot Log ကို စစ်ပါ။")
        except TelegramError:
            pass


def register_admin_pending_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("adminpending", admin_pending_command))
    application.add_handler(
        CallbackQueryHandler(admin_pending_callback, pattern=r"^adminpending:")
    )

import logging
from datetime import datetime, timedelta, timezone
from html import escape

from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.config import settings
from app.database.mongo import get_database

logger = logging.getLogger(__name__)
PAGE_SIZE = 8

EVENT_LABELS = {
    "purchase_request_created": "🛒 ဝယ်ယူမှု Request အသစ်",
    "seller_continue": "🤝 Seller က ဆက်လက်ညှိနှိုင်းရန် အတည်ပြု",
    "seller_mark_sold": "✅ Seller က Sold အဖြစ် သတ်မှတ်",
    "seller_mark_unresponsive": "⏳ Seller က Buyer တုံ့ပြန်မှုမရှိဟု သတ်မှတ်",
    "seller_release_listing": "↩️ Seller က Listing ပြန်ဖွင့်",
    "seller_cancel_listing": "🗑️ Seller က ရောင်းချမှု ပယ်ဖျက်",
    "seller_warning_sent": "🔔 Seller သတိပေးချက် ပို့ပြီး",
    "seller_decision_requested": "📌 Seller ဆုံးဖြတ်ချက် တောင်းဆိုပြီး",
    "admin_escalation_sent": "🚨 Admin ထံ Escalation ပို့ပြီး",
    "admin_keep_pending": "🕓 Admin က Pending ဆက်ထား",
    "admin_release_listing": "↩️ Admin က Listing ပြန်ဖွင့်",
    "admin_mark_sold": "✅ Admin က Sold အဖြစ် သတ်မှတ်",
}


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    try:
        return any(int(item) == int(user_id) for item in settings.admin_telegram_ids)
    except (TypeError, ValueError):
        return False


def _date_label(value) -> str:
    if not isinstance(value, datetime):
        return "အချိန်မသိရှိပါ"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(timezone(timedelta(hours=6, minutes=30)))
    return local.strftime("%Y-%m-%d %H:%M MMT")


async def _actor_label(db, actor_id: int | None, role: str) -> str:
    if role == "system":
        return "System"
    if actor_id is None:
        return escape(role.title())
    try:
        user_doc = await db.users.find_one({"_id": actor_id})
    except PyMongoError:
        logger.exception("Could not resolve audit actor %s", actor_id)
        user_doc = None
    if user_doc:
        username = (
            user_doc.get("username")
            or user_doc.get("telegram_username")
            or user_doc.get("user_name")
        )
        if username:
            name = "@" + str(username).strip().removeprefix("@")
            return f'<a href="https://t.me/{escape(name[1:])}">{escape(name)}</a>'
        name = user_doc.get("first_name") or user_doc.get("name")
        if name:
            return f'<a href="tg://user?id={actor_id}">{escape(str(name))}</a>'
    return f'<a href="tg://user?id={actor_id}">{escape(role.title())}</a>'


async def _render_page(target, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    db = get_database()
    page = max(0, page)
    try:
        total = await db.audit_logs.count_documents({})
        cursor = (
            db.audit_logs.find({})
            .sort([("created_at", -1)])
            .skip(page * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
        events = await cursor.to_list(length=PAGE_SIZE)
    except PyMongoError:
        logger.exception("Could not read audit log page %s", page)
        text = "Audit Log ကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။ MongoDB နဲ့ Bot log ကို စစ်ဆေးပါ။"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data=f"adminaudit:page:{page}")]])
        if hasattr(target, "edit_message_text"):
            await target.edit_message_text(text, reply_markup=markup)
        else:
            await target.reply_text(text, reply_markup=markup)
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= total_pages:
        page = total_pages - 1
        cursor = db.audit_logs.find({}).sort([("created_at", -1)]).skip(page * PAGE_SIZE).limit(PAGE_SIZE)
        events = await cursor.to_list(length=PAGE_SIZE)

    if not events:
        text = "🧾 <b>Marketplace Audit Log</b>\n\nမှတ်တမ်းအသစ် မရှိသေးပါ။"
    else:
        lines = [
            "🧾 <b>Marketplace Audit Log</b>",
            f"မှတ်တမ်းစုစုပေါင်း: <b>{total}</b> ခု · စာမျက်နှာ {page + 1}/{total_pages}",
            "",
        ]
        for item in events:
            details = item.get("details") or {}
            title = details.get("title")
            if not title and item.get("book_id") is not None:
                try:
                    book = await db.books.find_one({"_id": item.get("book_id")}, {"title": 1})
                    title = (book or {}).get("title")
                except PyMongoError:
                    logger.exception("Could not resolve book title for audit event %s", item.get("_id"))
            event_title = EVENT_LABELS.get(item.get("event_type"), str(item.get("event_type", "Marketplace event")))
            actor = await _actor_label(db, item.get("actor_id"), str(item.get("actor_role", "user")))
            lines.append(
                f"<b>{escape(event_title)}</b>\n"
                f"📚 {escape(str(title or 'စာအုပ်အမည် မသိရှိပါ'))}\n"
                f"👤 {actor}\n"
                f"🕒 {_date_label(item.get('created_at'))}"
            )
            transition = details.get("from_status") or details.get("to_status")
            if details.get("from_status") and details.get("to_status"):
                lines.append(
                    f"အခြေအနေ: {escape(str(details['from_status']))} → {escape(str(details['to_status']))}"
                )
            elif transition:
                lines.append(f"အခြေအနေ: {escape(str(transition))}")
            lines.append("")
        text = "\n".join(lines).strip()

    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ ယခင်", callback_data=f"adminaudit:page:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("နောက်တစ်မျက်နှာ ➡️", callback_data=f"adminaudit:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"adminaudit:page:{page}")])
    markup = InlineKeyboardMarkup(rows)

    if hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
        except TelegramError:
            message = getattr(target, "message", None)
            if message is None:
                raise
            await message.reply_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await target.reply_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)


async def admin_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if message is None:
        return
    if user is None or not is_admin(user.id):
        await message.reply_text("ဒီ command ကို Admin သာ အသုံးပြုနိုင်ပါတယ်။")
        return
    await _render_page(message, context, 0)


async def admin_audit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    user = query.from_user
    if not is_admin(user.id):
        await query.answer("Admin သာ အသုံးပြုနိုင်ပါတယ်။", show_alert=True)
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "adminaudit" or parts[1] != "page":
        await query.edit_message_text("Audit Log action မမှန်ကန်ပါ။")
        return
    try:
        page = int(parts[2])
    except ValueError:
        page = 0
    await _render_page(query, context, max(0, page))


def register_admin_audit_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("adminaudit", admin_audit_command))
    application.add_handler(CallbackQueryHandler(admin_audit_callback, pattern=r"^adminaudit:"))

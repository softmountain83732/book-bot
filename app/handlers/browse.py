#app/handlers/browse.py
"""Public listing browser with year/major filters, pagination and photo details."""
from __future__ import annotations

import logging
import re
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.mongo import get_database
from app.keyboards.book_actions import purchase_keyboard
from app.services.channel_service import format_semester

logger = logging.getLogger(__name__)
PAGE_SIZE = 5
MAJORS = {
    "all": "Major အားလုံး",
    "ceit": "CEIT",
    "ep": "EP",
    "ec": "EC",
    "archi": "Architecture",
    "mc": "MC",
    "me": "Mechanical",
    "civil": "Civil",
}
YEAR_OPTIONS = [("all", "Year အားလုံး")] + [(str(year), f"Year {year}") for year in range(1, 7)]


def _year_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for start in (0, 1, 3, 5):
        options = YEAR_OPTIONS[start:start + (1 if start == 0 else 2)]
        if options:
            rows.append([
                InlineKeyboardButton(label, callback_data=f"browse:year:{year}")
                for year, label in options
            ])
    rows.append([InlineKeyboardButton("🔎 စာအုပ်အမည်ဖြင့် ရှာရန်", callback_data="browse:search")])
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _major_keyboard(year_key: str) -> InlineKeyboardMarkup:
    rows = []
    keys = list(MAJORS.items())
    for i in range(0, len(keys), 2):
        rows.append([
            InlineKeyboardButton(label, callback_data=f"browse:list:{year_key}:{slug}:0")
            for slug, label in keys[i:i + 2]
        ])
    rows.append([InlineKeyboardButton("⬅️ Year ပြောင်းရန်", callback_data="browse:years")])
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _list_keyboard(
    books: list[dict], year_key: str, slug: str, offset: int, total: int
) -> InlineKeyboardMarkup:
    rows = []
    for book in books:
        title = str(book.get("title", "Untitled"))
        if len(title) > 38:
            title = title[:35] + "..."
        price = "ညှိနှိုင်း" if book.get("is_negotiable") else book.get("price") or "ဈေးမသတ်မှတ်"
        rows.append([InlineKeyboardButton(
            f"📚 {title} · {price}",
            callback_data=f"browse:detail:{book['_id']}:{year_key}:{slug}:{offset}",
        )])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            "⬅️ ယခင်", callback_data=f"browse:list:{year_key}:{slug}:{max(0, offset - PAGE_SIZE)}"
        ))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            "နောက်တစ်မျက်နှာ ➡️", callback_data=f"browse:list:{year_key}:{slug}:{offset + PAGE_SIZE}"
        ))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🎓 Filter ပြောင်းရန်", callback_data=f"browse:year:{year_key}")])
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _selected_filter_text(year_key: str, slug: str) -> str:
    year_label = "Year အားလုံး" if year_key == "all" else f"Year {year_key}"
    return f"{year_label} · {MAJORS.get(slug, MAJORS['all'])}"


def _listing_query(year_key: str, slug: str, keyword: str | None = None) -> dict:
    clauses: list[dict] = [
        {"status": "Available"},
        {"admin_hidden": {"$ne": True}},
    ]
    if year_key != "all":
        year_value = int(year_key)
        clauses.append({"$or": [{"year": year_value}, {"year": str(year_value)}]})
    if slug != "all":
        major_label = MAJORS[slug]
        clauses.append({"$or": [{"major_slug": slug}, {"major": major_label}]})
    if keyword:
        clauses.append({"title": {"$regex": re.escape(keyword), "$options": "i"}})
    return {"$and": clauses}


async def _show_list(
    target,
    year_key: str,
    slug: str,
    offset: int,
    keyword: str | None = None,
) -> None:
    if year_key not in {"all", "1", "2", "3", "4", "5", "6"}:
        year_key = "all"
    if slug not in MAJORS:
        slug = "all"
    offset = max(0, offset)
    mongo_query = _listing_query(year_key, slug, keyword)

    db = get_database()
    try:
        total = await db.books.count_documents(mongo_query)
        if total and offset >= total:
            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE
        cursor = db.books.find(mongo_query).sort("created_at", -1).skip(offset).limit(PAGE_SIZE)
        books = await cursor.to_list(length=PAGE_SIZE)
    except PyMongoError:
        logger.exception("Could not browse listings")
        text = "စာအုပ်စာရင်းကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။"
        markup = _year_keyboard()
    else:
        text = (
            f"📚 <b>{escape(_selected_filter_text(year_key, slug))} စာအုပ်များ</b>\n\n"
            f"ရောင်းရန်ရှိသော စာအုပ်: <b>{total}</b> ခု\n"
            "ဓာတ်ပုံနဲ့ အသေးစိတ်ကြည့်ရန် စာအုပ်ကို ရွေးချယ်ပါ။"
        )
        if keyword:
            text += f"\nရှာဖွေမှု: <b>{escape(keyword)}</b>"
        if not books:
            text += "\n\nလက်ရှိ Listing မရှိသေးပါ။"
        markup = _list_keyboard(books, year_key, slug, offset, total)

    if hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except TelegramError:
            message = getattr(target, "message", None)
            if message:
                await message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.reply_text(text, reply_markup=markup, parse_mode="HTML")


def _book_detail_text(book: dict) -> str:
    title = escape(str(book.get("title", "Untitled")))
    raw_price = book.get("price")
    if book.get("is_negotiable"):
        price = "ဈေးညှိနှိုင်း"
    elif isinstance(raw_price, (int, float)):
        price = f"{raw_price:,.0f} MMK"
    elif raw_price is not None and str(raw_price).strip():
        price = f"{escape(str(raw_price))} MMK"
    else:
        price = "ဈေးနှုန်း မသတ်မှတ်ထားပါ"
    return (
        f"📚 <b>{title}</b>\n\n"
        f"🎓 Major: {escape(str(book.get('major', 'N/A')))}\n"
        f"📖 Year: {escape(str(book.get('year', 'N/A')))}\n"
        f"📑 Semester: {escape(format_semester(book.get('year'), book.get('semester', 'N/A')))}\n"
        f"💰 ဈေးနှုန်း: {escape(price)}\n"
        f"📝 အခြေအနေ: {escape(str(book.get('condition', 'N/A')))}"
    )


def _detail_keyboard(
    book: dict,
    index: int,
    year_key: str,
    slug: str,
    offset: int,
    viewer_id: int,
) -> InlineKeyboardMarkup:
    book_id = str(book["_id"])
    photos = book.get("photo_file_ids") or ([book["photo_file_id"]] if book.get("photo_file_id") else [])
    rows: list[list[InlineKeyboardButton]] = []
    if len(photos) > 1:
        nav = []
        if index > 0:
            nav.append(InlineKeyboardButton(
                "⬅️ ယခင်ပုံ", callback_data=f"browse:photo:{book_id}:{index - 1}:{year_key}:{slug}:{offset}"
            ))
        nav.append(InlineKeyboardButton(f"{index + 1}/{len(photos)}", callback_data="browse:noop"))
        if index + 1 < len(photos):
            nav.append(InlineKeyboardButton(
                "နောက်ပုံ ➡️", callback_data=f"browse:photo:{book_id}:{index + 1}:{year_key}:{slug}:{offset}"
            ))
        rows.append(nav)

    actions = purchase_keyboard(book_id, book.get("status", "Available"))
    if actions:
        action_rows = list(actions.inline_keyboard)
        if book.get("seller_id") == viewer_id and action_rows:
            action_rows = action_rows[1:]
        rows.extend(action_rows)
    rows.append([InlineKeyboardButton("⬅️ စာအုပ်စာရင်း", callback_data="browse:back")])
    return InlineKeyboardMarkup(rows)


async def _send_book_detail(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    book: dict,
    year_key: str,
    slug: str,
    offset: int,
    index: int = 0,
) -> None:
    if book.get("status") != "Available" or book.get("admin_hidden"):
        await query.answer("ဒီစာအုပ်ကို ဝယ်ယူလို့ မရတော့ပါဘူး။", show_alert=True)
        return

    photos = book.get("photo_file_ids") or ([book["photo_file_id"]] if book.get("photo_file_id") else [])
    index = max(0, min(index, len(photos) - 1)) if photos else 0
    keyboard = _detail_keyboard(book, index, year_key, slug, offset, query.from_user.id)
    text = _book_detail_text(book)
    await query.answer()

    if photos:
        await query.message.reply_photo(
            photo=photos[index],
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    if context.args:
        await _show_list(message, "all", "all", 0, keyword=" ".join(context.args).strip())
    else:
        await message.reply_text("📖 အရင်ဆုံး Year ကို ရွေးချယ်ပါ။", reply_markup=_year_keyboard())


async def browse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    data = query.data
    parts = data.split(":")

    if data == "menu:browse" or data == "browse:years":
        await query.answer()
        await query.edit_message_text("📖 အရင်ဆုံး Year ကို ရွေးချယ်ပါ။", reply_markup=_year_keyboard())
        return

    if data == "browse:search":
        await query.answer()
        await query.edit_message_text(
            "စာအုပ်အမည်ဖြင့် ရှာရန် <code>/browse စာအုပ်အမည်</code> လို့ ရိုက်ထည့်ပါ။",
            parse_mode="HTML",
            reply_markup=_year_keyboard(),
        )
        return

    if data == "browse:noop":
        await query.answer()
        return

    if len(parts) == 3 and parts[:2] == ["browse", "year"]:
        year_key = parts[2]
        if year_key not in {"all", "1", "2", "3", "4", "5", "6"}:
            await query.answer("Year မမှန်ကန်ပါ။", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            f"🎓 {('Year အားလုံး' if year_key == 'all' else f'Year {year_key}')} အတွက် Major ကို ရွေးပါ။",
            reply_markup=_major_keyboard(year_key),
        )
        return

    if len(parts) == 5 and parts[:2] == ["browse", "list"]:
        try:
            offset = max(0, int(parts[4]))
        except ValueError:
            offset = 0
        await query.answer()
        await _show_list(query, parts[2], parts[3], offset)
        return

    # Backward compatibility for list buttons created by the previous Browse UI.
    if len(parts) == 4 and parts[:2] == ["browse", "list"]:
        try:
            offset = max(0, int(parts[3]))
        except ValueError:
            offset = 0
        await query.answer()
        await _show_list(query, "all", parts[2], offset)
        return

    if len(parts) == 6 and parts[:2] == ["browse", "detail"]:
        try:
            book_id = ObjectId(parts[2])
            offset = max(0, int(parts[5]))
        except (InvalidId, ValueError, TypeError):
            await query.answer("စာအုပ်အချက်အလက် မမှန်ကန်ပါ။", show_alert=True)
            return
        db = get_database()
        try:
            book = await db.books.find_one({"_id": book_id})
        except PyMongoError:
            logger.exception("Could not load browse detail for book %s", book_id)
            await query.answer("စာအုပ်အချက်အလက်ကို ရယူရာမှာ အမှားဖြစ်ပါတယ်။", show_alert=True)
            return
        if not book:
            await query.answer("ဒီ Listing ကို ရှာမတွေ့တော့ပါ။", show_alert=True)
            return
        await _send_book_detail(query, context, book, parts[3], parts[4], offset)
        return

    # Backward compatibility for detail buttons from the previous Browse UI.
    if len(parts) == 5 and parts[:2] == ["browse", "detail"]:
        try:
            book_id = ObjectId(parts[2])
            offset = max(0, int(parts[4]))
        except (InvalidId, ValueError, TypeError):
            await query.answer("စာအုပ်အချက်အလက် မမှန်ကန်ပါ။", show_alert=True)
            return
        db = get_database()
        book = await db.books.find_one({"_id": book_id})
        if not book:
            await query.answer("ဒီ Listing ကို ရှာမတွေ့တော့ပါ။", show_alert=True)
            return
        await _send_book_detail(query, context, book, "all", parts[3], offset)
        return

    if len(parts) == 7 and parts[:2] == ["browse", "photo"]:
        try:
            book_id = ObjectId(parts[2])
            index = int(parts[3])
            offset = max(0, int(parts[6]))
        except (InvalidId, ValueError, TypeError):
            await query.answer("ဓာတ်ပုံအချက်အလက် မမှန်ကန်ပါ။", show_alert=True)
            return
        db = get_database()
        book = await db.books.find_one({"_id": book_id})
        if not book or book.get("status") != "Available" or book.get("admin_hidden"):
            await query.answer("ဒီစာအုပ်ကို ဝယ်ယူလို့ မရတော့ပါဘူး။", show_alert=True)
            return
        photos = book.get("photo_file_ids") or ([book["photo_file_id"]] if book.get("photo_file_id") else [])
        if not photos or not 0 <= index < len(photos):
            await query.answer("ဓာတ်ပုံ မရှိတော့ပါ။", show_alert=True)
            return
        keyboard = _detail_keyboard(book, index, parts[4], parts[5], offset, query.from_user.id)
        await query.answer()
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(
                    media=photos[index],
                    caption=_book_detail_text(book),
                    parse_mode="HTML",
                ),
                reply_markup=keyboard,
            )
        except TelegramError:
            logger.exception("Could not switch browse photo for book %s", book_id)
            if query.message:
                try:
                    await query.message.reply_text("ဓာတ်ပုံပြောင်းလဲရာမှာ အမှားဖြစ်သွားပါတယ်။")
                except TelegramError:
                    logger.debug("Could not send browse photo error notice", exc_info=True)
        return

    if data == "browse:back":
        await query.answer()
        try:
            await query.message.delete()
        except TelegramError:
            logger.debug("Could not delete browse detail message", exc_info=True)
        return

    await query.answer("မသိရှိသော Browse Action ဖြစ်ပါတယ်။", show_alert=True)


def register_browse_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("browse", browse_command))
    application.add_handler(CallbackQueryHandler(browse_callback, pattern=r"^(?:menu:browse|browse:)") )

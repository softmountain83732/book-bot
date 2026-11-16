#	app/handlers/my_books.py
"""Seller's listing browser, status management and lightweight editor."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.database.mongo import get_database
from app.services.channel_service import (
    build_book_caption,
    format_semester,
    normalize_chat_id,
    update_book_channel,
)
from app.services.audit_service import record_audit_event
from app.keyboards.book_actions import purchase_keyboard

logger = logging.getLogger(__name__)
PAGE_SIZE = 5
EDIT_FIELD = 1
EDIT_VALUE = 2
EDIT_PHOTOS = 3
MAX_PHOTOS = 4


def _page_keyboard(books: list[dict], offset: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for book in books:
        title = str(book.get("title", "Untitled"))
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(
            f"📚 {title} · {book.get('status', 'Unknown')}",
            callback_data=f"mybooks:detail:{book['_id']}:{offset}",
        )])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️ ယခင်", callback_data=f"mybooks:list:{max(0, offset - PAGE_SIZE)}"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("နောက်တစ်မျက်နှာ ➡️", callback_data=f"mybooks:list:{offset + PAGE_SIZE}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _detail_keyboard(book: dict) -> InlineKeyboardMarkup:
    book_id = str(book["_id"])
    status = book.get("status")
    rows = []
    if status == "Available" and not book.get("admin_hidden"):
        rows.append([InlineKeyboardButton("✏️ Listing ပြင်ဆင်ရန်", callback_data=f"mybooks:edit:{book_id}")])
        rows.append([InlineKeyboardButton("⏸️ Delist · Buy Button ပိတ်ရန်", callback_data=f"mybooks:delist:{book_id}")])
    elif status == "Delisted":
        rows.append([InlineKeyboardButton("▶️ ပြန်လည်ရောင်းချရန်", callback_data=f"mybooks:relist:{book_id}")])

    if status != "Pending" and status != "Deleted":
        rows.append([InlineKeyboardButton("🗑️ Channel Post အပြီးဖျက်ရန်", callback_data=f"mybooks:delete:ask:{book_id}")])

    rows.append([InlineKeyboardButton("⬅️ စာအုပ်စာရင်း", callback_data="mybooks:list:0")])
    return InlineKeyboardMarkup(rows)


async def _show_list(target, user_id: int, offset: int = 0) -> None:
    db = get_database()
    try:
        query = {"seller_id": user_id, "status": {"$ne": "Deleted"}}
        total = await db.books.count_documents(query)
        if total and offset >= total:
            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE
        cursor = db.books.find(query).sort("created_at", -1).skip(offset).limit(PAGE_SIZE)
        books = await cursor.to_list(length=PAGE_SIZE)
    except PyMongoError:
        logger.exception("Could not load listings for seller %s", user_id)
        text = "ကိုယ်တင်ထားသောစာအုပ်များကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu:home")]])
    else:
        text = (
            "📖 <b>ကျွန်ုပ်၏စာအုပ်များ</b>\n\n"
            f"စာအုပ်စုစုပေါင်း: <b>{total}</b> ခု\n"
            "အသေးစိတ်ကြည့်ရန် စာအုပ်ကို ရွေးပါ။"
        )
        if not books:
            text += "\n\nစာအုပ် မတင်ရသေးပါ။"
        markup = _page_keyboard(books, offset, total)

    if hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except TelegramError:
            message = getattr(target, "message", None)
            if message:
                await message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def my_books_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user and message:
        await _show_list(message, user.id, 0)


async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or not query.data:
        return ConversationHandler.END
    await query.answer()
    raw_book_id = query.data.removeprefix("mybooks:edit:")
    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
        return ConversationHandler.END
    db = get_database()
    book = await db.books.find_one({"_id": book_id, "seller_id": user.id})
    if not book:
        await query.edit_message_text("ဒီစာအုပ်ကို မတွေ့ပါ။")
        return ConversationHandler.END
    if book.get("status") != "Available" or book.get("admin_hidden"):
        await query.edit_message_text("Available ဖြစ်နေသော Listing များကိုသာ ပြင်ဆင်နိုင်ပါတယ်။")
        return ConversationHandler.END

    context.user_data["mybooks_edit"] = {"book_id": str(book_id)}
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("စာအုပ်အမည်", callback_data="mybooks:field:title")],
        [InlineKeyboardButton("ဈေးနှုန်း", callback_data="mybooks:field:price")],
        [InlineKeyboardButton("အခြေအနေ", callback_data="mybooks:field:condition")],
        [InlineKeyboardButton("🖼️ စာအုပ်ပုံ ပြင်ဆင်ရန်", callback_data="mybooks:field:photos")],
        [InlineKeyboardButton("❌ ပယ်ဖျက်မည်", callback_data="mybooks:field:cancel")],
    ])
    await query.edit_message_text("ဘယ်အချက်အလက်ကို ပြင်ဆင်လိုပါသလဲ။", reply_markup=markup)
    return EDIT_FIELD


async def choose_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or not query.data:
        return EDIT_FIELD
    await query.answer()
    field = query.data.removeprefix("mybooks:field:")
    if field == "cancel":
        context.user_data.pop("mybooks_edit", None)
        await query.edit_message_text("ပြင်ဆင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")
        return ConversationHandler.END
    if field == "photos":
        context.user_data["mybooks_edit"] = {
            **context.user_data.get("mybooks_edit", {}),
            "field": "photos",
            "photo_file_ids": [],
        }
        await query.edit_message_text(
            "🖼️ စာအုပ်ပုံအသစ် ၁ ပုံမှ ၄ ပုံအထိ ပို့ပေးပါ။\n"
            "ပြီးသွားရင် <b>ဓာတ်ပုံပြီးပါပြီ</b> ကို နှိပ်ပါ။",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ဓာတ်ပုံပြီးပါပြီ", callback_data="mybooks:photos:done")],
                [InlineKeyboardButton("❌ မပြင်တော့ပါ", callback_data="mybooks:photos:cancel")],
            ]),
            parse_mode="HTML",
        )
        return EDIT_PHOTOS
    if field not in {"title", "price", "condition"}:
        await query.answer("Field မမှန်ကန်ပါ။", show_alert=True)
        return EDIT_FIELD
    context.user_data.setdefault("mybooks_edit", {})["field"] = field
    prompt = {
        "title": "စာအုပ်အမည်အသစ် ထည့်ပါ။",
        "price": "ဈေးနှုန်းအသစ် ထည့်ပါ။ ဈေးညှိနှိုင်းလိုပါက negotiable လို့ ရိုက်ပါ။",
        "condition": "စာအုပ်အခြေအနေအသစ် ထည့်ပါ။",
    }[field]
    await query.edit_message_text(prompt)
    return EDIT_VALUE


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("mybooks_edit", None)
    if update.effective_message:
        await update.effective_message.reply_text("ပြင်ဆင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")
    return ConversationHandler.END


async def receive_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    message = update.effective_message
    state = context.user_data.get("mybooks_edit") or {}
    if user is None or message is None or not state.get("book_id"):
        return ConversationHandler.END

    field = state.get("field")
    raw = (message.text or "").strip()
    set_fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if field == "title":
        if not 2 <= len(raw) <= 120:
            await message.reply_text("စာအုပ်အမည်ကို စာလုံး ၂ လုံးမှ ၁၂၀ အတွင်း ထည့်ပါ။")
            return EDIT_VALUE
        set_fields["title"] = raw
    elif field == "condition":
        if not raw or len(raw) > 250:
            await message.reply_text("အခြေအနေကို စာလုံး ၁ မှ ၂၅၀ အတွင်း ထည့်ပါ။")
            return EDIT_VALUE
        set_fields["condition"] = raw
    elif field == "price":
        normalized = raw.lower().replace(",", "")
        if normalized in {"negotiable", "ညှိနှိုင်း", "ဈေးညှိနှိုင်း"}:
            set_fields.update({"price": None, "is_negotiable": True})
        else:
            try:
                price = float(normalized)
                if price <= 0 or price > 1_000_000_000:
                    raise ValueError
            except ValueError:
                await message.reply_text("ဈေးနှုန်းကို အပေါင်းဂဏန်းနဲ့ ထည့်ပါ၊ သို့မဟုတ် negotiable လို့ ရိုက်ပါ။")
                return EDIT_VALUE
            set_fields.update({"price": int(price) if price.is_integer() else price, "is_negotiable": False})
    else:
        await message.reply_text("ပြင်ဆင်မည့် Field မမှန်ကန်ပါ။")
        return ConversationHandler.END

    try:
        book_id = ObjectId(state["book_id"])
        db = get_database()
        result = await db.books.update_one(
            {"_id": book_id, "seller_id": user.id, "status": "Available", "admin_hidden": {"$ne": True}},
            {"$set": set_fields},
        )
        if result.modified_count != 1:
            await message.reply_text("Listing ကို မပြင်နိုင်တော့ပါ။ Status ပြောင်းလဲသွားနိုင်ပါတယ်။")
            return ConversationHandler.END
        book = await db.books.find_one({"_id": book_id})
        if book and book.get("channel_message_id") and book.get("channel_id"):
            try:
                await update_book_channel(context.bot, book)
                await db.books.update_one({"_id": book_id}, {"$unset": {"channel_sync_error": ""}})
            except Exception:
                logger.exception("Could not sync edited book %s to channel", book_id)
                await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})
        await message.reply_text("✅ Listing ကို ပြင်ဆင်ပြီးပါပြီ။")
    except (InvalidId, PyMongoError):
        logger.exception("Could not edit listing for seller %s", user.id)
        await message.reply_text("Listing ကို ပြင်ဆင်ရာမှာ အမှားဖြစ်သွားပါတယ်။")
    finally:
        context.user_data.pop("mybooks_edit", None)
    return ConversationHandler.END


async def receive_replacement_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    state = context.user_data.get("mybooks_edit") or {}
    if message is None or not message.photo or state.get("field") != "photos":
        return EDIT_PHOTOS

    photos = state.setdefault("photo_file_ids", [])
    file_id = message.photo[-1].file_id
    if file_id not in photos:
        if len(photos) >= MAX_PHOTOS:
            await message.reply_text("ဓာတ်ပုံ ၄ ပုံ ပြည့်ပါပြီ။ အောက်က ဓာတ်ပုံပြီးပါပြီ ကို နှိပ်ပါ။")
            return EDIT_PHOTOS
        photos.append(file_id)

    await message.reply_text(
        f"✅ ပုံအသစ် {len(photos)}/{MAX_PHOTOS} ပုံ ရရှိပါပြီ။",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ဓာတ်ပုံပြီးပါပြီ", callback_data="mybooks:photos:done")],
            [InlineKeyboardButton("❌ မပြင်တော့ပါ", callback_data="mybooks:photos:cancel")],
        ]),
    )
    return EDIT_PHOTOS


async def finish_replacement_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    state = context.user_data.get("mybooks_edit") or {}
    if query is None or user is None:
        return ConversationHandler.END
    await query.answer()

    photo_ids = list(dict.fromkeys(state.get("photo_file_ids") or []))[:MAX_PHOTOS]
    if not photo_ids:
        await query.answer("အနည်းဆုံး ပုံ ၁ ပုံ ပို့ပေးပါ။", show_alert=True)
        return EDIT_PHOTOS

    try:
        book_id = ObjectId(state["book_id"])
    except (KeyError, InvalidId, TypeError):
        await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
        context.user_data.pop("mybooks_edit", None)
        return ConversationHandler.END

    db = get_database()
    book = await db.books.find_one({
        "_id": book_id,
        "seller_id": user.id,
        "status": "Available",
        "admin_hidden": {"$ne": True},
    })
    if not book:
        await query.edit_message_text("ဒီ Listing ကို ပြင်ဆင်လို့ မရတော့ပါဘူး။")
        context.user_data.pop("mybooks_edit", None)
        return ConversationHandler.END

    # Publish the replacement first. Only remove the old channel messages after
    # the new post and database references have been saved successfully.
    old_ids = []
    old_ids.extend(book.get("channel_photo_message_ids") or [])
    if book.get("channel_message_id"):
        old_ids.append(book["channel_message_id"])
    if not old_ids and book.get("channel_message_id"):
        old_ids = [book["channel_message_id"]]
    old_ids = list(dict.fromkeys(int(x) for x in old_ids if x is not None))

    channel_id = book.get("channel_id")
    new_message_ids = []
    new_photo_message_ids = []
    new_post_type = "photo"
    new_action_message_id = None

    try:
        if channel_id:
            channel_id = normalize_chat_id(channel_id)
            updated_book = dict(book)
            updated_book["photo_file_id"] = photo_ids[0]
            updated_book["photo_file_ids"] = photo_ids
            caption = build_book_caption(updated_book)
            keyboard = purchase_keyboard(str(book_id), book.get("status", "Available"))

            if len(photo_ids) == 1:
                posted = await context.bot.send_photo(
                    chat_id=channel_id,
                    photo=photo_ids[0],
                    caption=caption,
                    reply_markup=keyboard,
                )
                new_action_message_id = posted.message_id
                new_message_ids.append(posted.message_id)
                new_photo_message_ids = [posted.message_id]
                new_post_type = "photo"
            else:
                media_messages = await context.bot.send_media_group(
                    chat_id=channel_id,
                    media=[InputMediaPhoto(media=file_id) for file_id in photo_ids],
                )
                new_photo_message_ids = [item.message_id for item in media_messages]
                new_message_ids.extend(new_photo_message_ids)
                action_post = await context.bot.send_message(
                    chat_id=channel_id,
                    text=caption,
                    reply_markup=keyboard,
                )
                new_action_message_id = action_post.message_id
                new_message_ids.append(action_post.message_id)
                new_post_type = "text"

        set_fields = {
            "photo_file_id": photo_ids[0],
            "photo_file_ids": photo_ids,
            "updated_at": datetime.now(timezone.utc),
        }
        if channel_id:
            set_fields.update({
                "channel_message_id": new_action_message_id,
                "channel_photo_message_ids": new_photo_message_ids,
                "channel_post_type": new_post_type,
                "channel_sync_error": False,
            })

        result = await db.books.update_one(
            {"_id": book_id, "seller_id": user.id, "status": "Available", "admin_hidden": {"$ne": True}},
            {"$set": set_fields},
        )
        if result.modified_count != 1:
            raise RuntimeError("Listing changed while replacing photos")

        # Remove the old album/post after the new version is safely published.
        if channel_id:
            for old_id in old_ids:
                if old_id in new_message_ids:
                    continue
                try:
                    await context.bot.delete_message(chat_id=channel_id, message_id=old_id)
                except TelegramError:
                    logger.warning("Could not delete old listing photo message %s", old_id)

        await query.edit_message_text(
            f"✅ Listing ပုံတွေကို ပြင်ဆင်ပြီးပါပြီ။ (ပုံ {len(photo_ids)} ပုံ)"
        )
    except Exception:
        logger.exception("Could not replace photos for book %s", book_id)
        # If publishing failed before database update, clean up any partial new posts.
        for message_id in new_message_ids:
            try:
                await context.bot.delete_message(chat_id=channel_id, message_id=message_id)
            except TelegramError:
                pass
        await query.edit_message_text("ဓာတ်ပုံပြင်ဆင်ရာမှာ အမှားဖြစ်သွားပါတယ်။ အရင်ပုံတွေကို မဖျက်ထားပါဘူး။")
    finally:
        context.user_data.pop("mybooks_edit", None)

    return ConversationHandler.END


async def _photo_input_hint(update: Update) -> int:
    if update.effective_message:
        await update.effective_message.reply_text("ဓာတ်ပုံကို Photo အနေနဲ့ ပို့ပေးပါ။")
    return EDIT_PHOTOS


async def cancel_replacement_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer("ဓာတ်ပုံပြင်ဆင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")
        await query.edit_message_text("ဓာတ်ပုံပြင်ဆင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")
    context.user_data.pop("mybooks_edit", None)
    return ConversationHandler.END


async def _delete_channel_listing_posts(bot, book: dict) -> bool:
    """Delete every Telegram message belonging to a single/album listing."""
    channel_id = book.get("channel_id")
    if not channel_id:
        return True
    message_ids = list(book.get("channel_photo_message_ids") or [])
    if book.get("channel_message_id"):
        message_ids.append(book["channel_message_id"])
    message_ids = list(dict.fromkeys(int(value) for value in message_ids if value is not None))
    if not message_ids:
        return True

    success = True
    normalized_channel = normalize_chat_id(channel_id)
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=normalized_channel, message_id=message_id)
        except TelegramError:
            success = False
            logger.warning("Could not delete channel post %s for book %s", message_id, book.get("_id"), exc_info=True)
    return success


async def _set_listing_status(query, context, user_id: int, book_id: ObjectId, old_status: str, new_status: str, success_text: str) -> None:
    db = get_database()
    now = datetime.now(timezone.utc)
    result = await db.books.update_one(
        {"_id": book_id, "seller_id": user_id, "status": old_status, "admin_hidden": {"$ne": True}},
        {"$set": {"status": new_status, "updated_at": now}},
    )
    if result.modified_count != 1:
        await query.edit_message_text("ဒီ Listing ရဲ့ Status ပြောင်းလဲသွားပါပြီ။ ပြန်စစ်ပေးပါ။")
        return

    book = await db.books.find_one({"_id": book_id, "seller_id": user_id})
    sync_ok = True
    if book and book.get("channel_message_id"):
        try:
            await update_book_channel(context.bot, book, status=new_status)
        except Exception:
            sync_ok = False
            logger.exception("Could not synchronize %s listing %s to channel", new_status, book_id)
            await db.books.update_one({"_id": book_id}, {"$set": {"channel_sync_error": True}})
        else:
            await db.books.update_one({"_id": book_id}, {"$unset": {"channel_sync_error": ""}})

    event_type = "seller_delist_listing" if new_status == "Delisted" else "seller_relist_listing"
    await record_audit_event(
        db,
        event_type=event_type,
        actor_id=user_id,
        actor_role="seller",
        book_id=book_id,
        details={"title": str(book.get("title", "Untitled")) if book else "Untitled", "from_status": old_status, "to_status": new_status},
    )
    text = success_text
    if not sync_ok:
        text += "\n⚠️ Database Status ပြောင်းပြီးပါပြီ၊ Channel Post Sync မှာ အမှားရှိလို့ Admin က စစ်ဆေးရန် လိုပါတယ်။"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 စာအုပ်အသေးစိတ်", callback_data=f"mybooks:detail:{book_id}:0")],
        [InlineKeyboardButton("⬅️ ကျွန်ုပ်၏စာအုပ်များ", callback_data="mybooks:list:0")],
    ]))


async def _confirm_delete_listing(query, context, user_id: int, raw_book_id: str) -> None:
    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
        return
    book = await get_database().books.find_one({"_id": book_id, "seller_id": user_id})
    if not book or book.get("status") == "Deleted":
        await query.edit_message_text("ဒီ Listing ကို မတွေ့ပါ။")
        return
    if book.get("status") == "Pending":
        await query.edit_message_text("⏳ Purchase Request Pending ဖြစ်နေပါတယ်။ Seller ဘက်က Request ကို အရင်ဆုံး ဖြေရှင်းပြီးမှ Post ဖျက်နိုင်ပါတယ်။")
        return
    await query.edit_message_text(
        "⚠️ <b>Channel Post ကို အပြီးဖျက်မှာ သေချာပါသလား။</b>\n\n"
        f"📚 {escape(str(book.get('title', 'Untitled')))}\n\n"
        "ဒီလုပ်ဆောင်ချက်က Channel ပေါ်က ဓာတ်ပုံ/စာသား Post အားလုံးကို ဖျက်ပါမယ်။\n"
        "Database မှာတော့ Purchase History နဲ့ Audit အတွက် Deleted မှတ်တမ်းကို ထိန်းသိမ်းထားပါမယ်။",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ ဟုတ်ကဲ့၊ Post ဖျက်မည်", callback_data=f"mybooks:delete:confirm:{book_id}")],
            [InlineKeyboardButton("↩️ မဖျက်တော့ပါ", callback_data=f"mybooks:delete:keep:{book_id}")],
        ]),
    )


async def _delete_listing_permanently(query, context, user_id: int, raw_book_id: str) -> None:
    try:
        book_id = ObjectId(raw_book_id)
    except (InvalidId, TypeError):
        await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
        return

    db = get_database()
    book = await db.books.find_one({"_id": book_id, "seller_id": user_id})
    if not book or book.get("status") == "Deleted":
        await query.edit_message_text("ဒီ Listing ကို မတွေ့ပါ။")
        return
    if book.get("status") == "Pending":
        await query.edit_message_text("Purchase Request Pending ဖြစ်နေတဲ့အတွက် အခုဖျက်လို့မရပါဘူး။ အရင်ဆုံး Request ကို ဖြေရှင်းပါ။")
        return

    active_request = await db.purchase_requests.find_one({"book_id": book_id, "status": "Pending"})
    if active_request:
        await query.edit_message_text("Pending Purchase Request ရှိနေတဲ့အတွက် Post ကို မဖျက်နိုင်သေးပါ။")
        return

    now = datetime.now(timezone.utc)
    result = await db.books.update_one(
        {"_id": book_id, "seller_id": user_id, "status": {"$nin": ["Pending", "Deleted"]}},
        {"$set": {"status": "Deleted", "admin_hidden": True, "deleted_at": now, "deleted_by": user_id, "updated_at": now}},
    )
    if result.modified_count != 1:
        await query.edit_message_text("ဒီ Listing ရဲ့ အခြေအနေ ပြောင်းလဲသွားလို့ ဖျက်လို့မရတော့ပါဘူး။")
        return

    channel_deleted = await _delete_channel_listing_posts(context.bot, book)
    channel_buttons_removed = False
    if not channel_deleted:
        # Telegram may reject deletion of older posts or due to missing admin
        # rights. As a fallback, remove the inline actions so a stale Buy
        # button cannot remain usable on a Deleted listing.
        try:
            await update_book_channel(
                context.bot,
                {**book, "status": "Deleted"},
                status="Deleted",
            )
            channel_buttons_removed = True
        except Exception:
            logger.exception("Could not disable actions on undeleted channel post for book %s", book_id)

    await db.books.update_one(
        {"_id": book_id},
        {"$set": {
            "channel_delete_error": not channel_deleted,
            "channel_deleted_at": now if channel_deleted else None,
            "channel_buttons_removed": channel_buttons_removed,
        }},
    )
    await record_audit_event(
        db,
        event_type="seller_delete_listing_post",
        actor_id=user_id,
        actor_role="seller",
        book_id=book_id,
        details={"title": str(book.get("title", "Untitled")), "from_status": book.get("status"), "to_status": "Deleted", "channel_deleted": channel_deleted},
    )
    if channel_deleted:
        text = "🗑️ Channel Post ကို ဖျက်ပြီးပါပြီ။ Listing ကို Marketplace မှာလည်း ဖယ်ရှားထားပါတယ်။"
    elif channel_buttons_removed:
        text = (
            "✅ Listing ကို Marketplace မှာ ဖယ်ရှားပြီး Buy Action ကို ပိတ်ထားပါတယ်။\n"
            "⚠️ Telegram က Channel Post အချို့ကို အပြီးဖျက်ခွင့်မပေးခဲ့ပါ။ Admin က စစ်ဆေးရန် လိုပါတယ်။"
        )
    else:
        text = (
            "✅ Listing ကို Marketplace မှာ ဖယ်ရှားထားပါတယ်။\n"
            "⚠️ Channel Post ကို မဖျက်နိုင်သလို Button များကိုလည်း မပိတ်နိုင်ခဲ့ပါ။ Admin ကို အသိပေးထားပါတယ်။"
        )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ ကျွန်ုပ်၏စာအုပ်များ", callback_data="mybooks:list:0")]
    ]))


async def my_books_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or not query.data or user is None:
        return
    data = query.data
    await query.answer()
    if data == "menu:my_books":
        await _show_list(query, user.id, 0)
        return
    parts = data.split(":")
    if len(parts) == 3 and parts[:2] == ["mybooks", "list"]:
        try:
            offset = max(0, int(parts[2]))
        except ValueError:
            offset = 0
        await _show_list(query, user.id, offset)
        return
    if len(parts) == 4 and parts[:2] == ["mybooks", "detail"]:
        try:
            book_id = ObjectId(parts[2])
            offset = max(0, int(parts[3]))
        except (InvalidId, ValueError, TypeError):
            await query.edit_message_text("စာအုပ်အချက်အလက် မမှန်ကန်ပါ။")
            return
        db = get_database()
        book = await db.books.find_one({"_id": book_id, "seller_id": user.id})
        if not book:
            await query.edit_message_text("ဒီစာအုပ်ကို မတွေ့ပါ။")
            return
        title = escape(str(book.get("title", "Untitled")))
        price = "ဈေးညှိနှိုင်း" if book.get("is_negotiable") else f"{book.get('price', 0):,} MMK"
        text = (
            f"📚 <b>{title}</b>\n\n"
            f"Major: {escape(str(book.get('major', 'N/A')))}\n"
            f"Year: {escape(str(book.get('year', 'N/A')))} · Semester: {escape(format_semester(book.get('year'), book.get('semester', 'N/A')))}\n"
            f"Price: {escape(price)}\n"
            f"Condition: {escape(str(book.get('condition', 'N/A')))}\n"
            f"Status: <b>{escape(str(book.get('status', 'Unknown')))}</b>"
        )
        if book.get("status") == "Pending":
            text += "\n\n⏳ Purchase Request Pending ဖြစ်နေတဲ့အတွက် Delist/Delete ကို ခဏပိတ်ထားပါတယ်။"
        await query.edit_message_text(text, reply_markup=_detail_keyboard(book), parse_mode="HTML")
        return
    if len(parts) == 3 and parts[:2] == ["mybooks", "delist"]:
        try:
            book_id = ObjectId(parts[2])
        except (InvalidId, TypeError):
            await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
            return
        await _set_listing_status(
            query, context, user.id, book_id, "Available", "Delisted",
            "⏸️ Listing ကို Delist လုပ်ပြီး Buy Button ကို ပိတ်ထားပါပြီ။ ပြန်လည်ရောင်းချနိုင်ပါတယ်။",
        )
        return

    if len(parts) == 3 and parts[:2] == ["mybooks", "relist"]:
        try:
            book_id = ObjectId(parts[2])
        except (InvalidId, TypeError):
            await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
            return
        await _set_listing_status(
            query, context, user.id, book_id, "Delisted", "Available",
            "▶️ Listing ကို ပြန်ဖွင့်ပြီး Buy Button ကို အသက်သွင်းပြီးပါပြီ။",
        )
        return

    if len(parts) == 4 and parts[:3] == ["mybooks", "delete", "ask"]:
        await _confirm_delete_listing(query, context, user.id, parts[3])
        return

    if len(parts) == 4 and parts[:3] == ["mybooks", "delete", "keep"]:
        await query.edit_message_text(
            "ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ ကျွန်ုပ်၏စာအုပ်များ", callback_data="mybooks:list:0")]
            ]),
        )
        return

    if len(parts) == 4 and parts[:3] == ["mybooks", "delete", "confirm"]:
        await _delete_listing_permanently(query, context, user.id, parts[3])
        return

    # Old Cancel buttons still open the safe Delist action after an update.
    if len(parts) == 3 and parts[:2] == ["mybooks", "cancel"]:
        try:
            book_id = ObjectId(parts[2])
        except (InvalidId, TypeError):
            await query.edit_message_text("စာအုပ် ID မမှန်ကန်ပါ။")
            return
        await _set_listing_status(
            query, context, user.id, book_id, "Available", "Delisted",
            "⏸️ Listing ကို Delist လုပ်ပြီး Buy Button ကို ပိတ်ထားပါပြီ။",
        )
        return



def register_my_books_handler(application: Application) -> None:
    edit_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern=r"^mybooks:edit:[0-9a-fA-F]{24}$")],
        states={
            EDIT_FIELD: [CallbackQueryHandler(choose_edit_field, pattern=r"^mybooks:field:")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_value)],
            EDIT_PHOTOS: [
                CallbackQueryHandler(finish_replacement_photos, pattern=r"^mybooks:photos:done$"),
                CallbackQueryHandler(cancel_replacement_photos, pattern=r"^mybooks:photos:cancel$"),
                MessageHandler(filters.PHOTO, receive_replacement_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, _photo_input_hint),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_edit)],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )
    application.add_handler(edit_conversation)
    application.add_handler(CommandHandler("mybooks", my_books_command))
    application.add_handler(CallbackQueryHandler(
        my_books_callback,
        pattern=r"^(?:menu:my_books|mybooks:(?:list:|detail:|cancel:|delist:|relist:|delete:))",
    ))

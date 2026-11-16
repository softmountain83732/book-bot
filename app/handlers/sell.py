#app/handlers/sell.py
"""Conversation for creating and publishing a book listing."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.config import settings
from app.database.mongo import get_database
from app.keyboards.book_actions import purchase_keyboard
from app.services.channel_service import build_book_caption, normalize_chat_id
from app.services.user_service import register_user

logger = logging.getLogger(__name__)

TITLE, MAJOR, YEAR, SEMESTER, PRICE, CONDITION, PHOTO = range(7)

MAX_PHOTOS = 4

MAJORS = {
    "ceit": "CEIT",
    "ep": "EP",
    "ec": "EC",
    "archi": "Architecture",
    "mc": "MC",
    "me": "Mechanical",
    "civil": "Civil",
}


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ ရောင်းချမှု ပယ်ဖျက်မည်", callback_data="sell:cancel")]
    ])


def _major_keyboard() -> InlineKeyboardMarkup:
    rows = []
    items = list(MAJORS.items())

    for index in range(0, len(items), 2):
        rows.append([
            InlineKeyboardButton(label, callback_data=f"sell:major:{slug}")
            for slug, label in items[index:index + 2]
        ])

    rows.append([
        InlineKeyboardButton("❌ Cancel", callback_data="sell:cancel")
    ])

    return InlineKeyboardMarkup(rows)


def _year_keyboard() -> InlineKeyboardMarkup:
    rows = []

    for start in (1, 3, 5):
        rows.append([
            InlineKeyboardButton(
                f"Year {year}",
                callback_data=f"sell:year:{year}",
            )
            for year in range(start, min(start + 2, 7))
        ])

    rows.append([
        InlineKeyboardButton("❌ Cancel", callback_data="sell:cancel")
    ])

    return InlineKeyboardMarkup(rows)


def _semester_values(year) -> tuple[int, int, str]:
    """Return the two semester numbers and Both value for a selected year."""
    return (3, 4, "3 & 4") if str(year).strip() == "2" else (1, 2, "1 & 2")


def _semester_keyboard(year) -> InlineKeyboardMarkup:
    first, second, both_value = _semester_values(year)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Semester {first}",
                callback_data=f"sell:semester:{first}",
            ),
            InlineKeyboardButton(
                f"Semester {second}",
                callback_data=f"sell:semester:{second}",
            ),
        ],
        [
            InlineKeyboardButton(
                f"📚 နှစ်ခုလုံး ({first} & {second})",
                callback_data="sell:semester:both",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="sell:cancel",
            )
        ],
    ])


def _photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ ဓာတ်ပုံပြီးပါပြီ · Listing တင်မည်",
                callback_data="sell:photos:done",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ ရောင်းချမှု ပယ်ဖျက်မည်",
                callback_data="sell:cancel",
            )
        ],
    ])


def _price_prompt() -> str:
    return (
        "ဈေးနှုန်းကို MMK နဲ့ ထည့်ပေးပါ။\n"
        "ဈေးညှိနှိုင်းလိုပါက <code>negotiable</code> လို့ ရိုက်ပါ။"
    )


def _track_sell_prompt(context: ContextTypes.DEFAULT_TYPE, message) -> None:
    if message is None or not getattr(message, "message_id", None):
        return
    draft = context.user_data.get("sell_draft")
    if not isinstance(draft, dict):
        return
    ids = draft.setdefault("bot_prompt_message_ids", [])
    if message.message_id not in ids:
        ids.append(message.message_id)


async def _reply_sell_prompt(message, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    sent = await message.reply_text(*args, **kwargs)
    _track_sell_prompt(context, sent)
    return sent


async def _edit_sell_prompt(query, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    _track_sell_prompt(context, getattr(query, "message", None))
    return await query.edit_message_text(*args, **kwargs)


def _derive_sell_state(draft: dict) -> int:
    if "title" not in draft:
        return TITLE
    if "major" not in draft:
        return MAJOR
    if "year" not in draft:
        return YEAR
    if "semester" not in draft:
        return SEMESTER
    if "is_negotiable" not in draft:
        return PRICE
    if "condition" not in draft:
        return CONDITION
    return PHOTO


def _resume_sell_prompt(state: int, draft: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    prompts = {
        TITLE: ("စာအုပ်အမည်ကို ရိုက်ထည့်ပေးပါ။", _cancel_keyboard()),
        MAJOR: ("သက်ဆိုင်ရာ Major ကို ရွေးချယ်ပါ။", _major_keyboard()),
        YEAR: ("📖 ဘယ်နှစ် Year လဲ။ အောက်မှာ ရွေးချယ်ပါ။", _year_keyboard()),
        PRICE: (_price_prompt(), _cancel_keyboard()),
        CONDITION: ("စာအုပ်အခြေအနေကို ဖော်ပြပေးပါ။ (ဥပမာ New, Good, Used)", _cancel_keyboard()),
    }
    if state == SEMESTER:
        return ("📑 ဘယ် Semester အတွက်လဲ။", _semester_keyboard(draft.get("year")))
    if state != PHOTO:
        return prompts.get(state, prompts[TITLE])
    count = len(draft.get("photo_file_ids") or [])
    return (
        f"📸 ဓာတ်ပုံ {count}/{MAX_PHOTOS} ပုံ ရရှိထားပါတယ်။\n"
        "နောက်ထပ်ပုံများ ပို့နိုင်ပါတယ်။ ပြီးသွားရင် ဓာတ်ပုံပြီးပါပြီ ကို နှိပ်ပါ။",
        _photo_keyboard(),
    )


async def _save_sell_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> None:
    user = update.effective_user
    chat = update.effective_chat
    draft = context.user_data.get("sell_draft")
    if user is None or chat is None or not isinstance(draft, dict):
        return
    draft["state"] = int(state)
    draft["chat_id"] = chat.id
    try:
        await get_database().sell_drafts.update_one(
            {"_id": user.id},
            {"$set": {"user_id": user.id, "chat_id": chat.id, "state": int(state), "draft": draft,
                      "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except PyMongoError:
        logger.exception("Could not persist active sell draft for user %s", user.id)


async def _delete_sell_draft(user_id: int | None) -> None:
    if user_id is None:
        return
    try:
        await get_database().sell_drafts.delete_one({"_id": user_id})
    except PyMongoError:
        logger.exception("Could not delete completed sell draft for user %s", user_id)


async def _cleanup_sell_prompts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete only messages sent by the bot during this /sell flow."""
    draft = context.user_data.get("sell_draft") or {}
    chat = update.effective_chat
    chat_id = chat.id if chat else draft.get("chat_id")
    if chat_id is None:
        return
    message_ids = list(draft.get("bot_prompt_message_ids") or [])
    message_ids.extend(draft.get("photo_notice_message_ids") or [])
    for message_id in dict.fromkeys(message_ids):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=int(message_id))
        except TelegramError:
            logger.debug("Could not delete sell prompt message %s", message_id, exc_info=True)


async def start_sell(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return ConversationHandler.END
    if message.chat.type != "private":
        await _reply_sell_prompt(message, context, "စာအုပ်တင်ခြင်းကို Bot Private Chat မှာသာ လုပ်ဆောင်နိုင်ပါတယ်။")
        return ConversationHandler.END

    try:
        await register_user(user)
    except PyMongoError:
        logger.exception("Could not register seller %s", user.id)
        await _reply_sell_prompt(message, context, "User အချက်အလက်ကို သိမ်းရာမှာ အမှားဖြစ်သွားပါတယ်။")
        return ConversationHandler.END

    # MongoDB is the durable source of truth for the latest /sell draft.
    # PTB PicklePersistence still restores the ConversationHandler state, but
    # the Mongo copy protects the user's entered fields if the pickle is stale
    # or the process is restarted before its next persistence interval.
    try:
        saved = await get_database().sell_drafts.find_one({"_id": user.id})
    except PyMongoError:
        logger.exception("Could not load saved sell draft for user %s", user.id)
        saved = None

    draft = context.user_data.get("sell_draft")
    if saved and isinstance(saved.get("draft"), dict):
        draft = saved["draft"]
        context.user_data["sell_draft"] = draft
        state = saved.get("state", _derive_sell_state(draft))
    elif isinstance(draft, dict):
        state = draft.get("state", _derive_sell_state(draft))
    else:
        state = None

    if isinstance(draft, dict):
        if str(draft.get("year", "")).strip() == "2" and "semester" in draft:
            legacy_semester = str(draft.get("semester")).strip().lower()
            legacy_year2_map = {
                "1": 3,
                "2": 4,
                "both": "3 & 4",
                "1&2": "3 & 4",
                "1 & 2": "3 & 4",
            }
            if legacy_semester in legacy_year2_map:
                draft["semester"] = legacy_year2_map[legacy_semester]
        if state not in {TITLE, MAJOR, YEAR, SEMESTER, PRICE, CONDITION, PHOTO}:
            state = _derive_sell_state(draft)
        resume_text, resume_markup = _resume_sell_prompt(state, draft)
        resume_header = "🔄 <b>မပြီးသေးတဲ့ စာအုပ်တင်ခြင်းကို ပြန်ဆက်ပါမယ်။</b>\n\n"
        if update.callback_query:
            await update.callback_query.answer()
            _track_sell_prompt(context, update.callback_query.message)
            await _edit_sell_prompt(
                update.callback_query,
                context,
                resume_header + resume_text,
                reply_markup=resume_markup,
                parse_mode=ParseMode.HTML,
            )
        else:
            await _reply_sell_prompt(
                message,
                context,
                resume_header + resume_text,
                reply_markup=resume_markup,
                parse_mode=ParseMode.HTML,
            )
        await _save_sell_draft(update, context, state)
        return state

    context.user_data["sell_draft"] = {
        "photo_file_ids": [],
        "photo_notice_message_ids": [],
        "bot_prompt_message_ids": [],
    }
    prompt = (
        "📤 <b>စာအုပ်အသစ်တင်ရန်</b>\n\n"
        "စာအုပ်အမည်ကို ရိုက်ထည့်ပေးပါ။\n"
        "အဆင့်တိုင်းမှာ Cancel Button ဖြင့် ပယ်ဖျက်နိုင်ပါတယ်။"
    )
    if update.callback_query:
        await update.callback_query.answer()
        _track_sell_prompt(context, update.callback_query.message)
        await _edit_sell_prompt(update.callback_query, context, prompt,
                                reply_markup=_cancel_keyboard(), parse_mode=ParseMode.HTML)
    else:
        await _reply_sell_prompt(message, context, prompt,
                                 reply_markup=_cancel_keyboard(), parse_mode=ParseMode.HTML)
    await _save_sell_draft(update, context, TITLE)
    return TITLE


async def receive_title(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    message = update.effective_message

    title = (message.text or "").strip() if message else ""

    if len(title) < 2 or len(title) > 120:
        await _reply_sell_prompt(message, context,
            "စာအုပ်အမည်ကို စာလုံး ၂ လုံးမှ ၁၂၀ အတွင်း ထည့်ပါ။",
            reply_markup=_cancel_keyboard(),
        )
        await _save_sell_draft(update, context, TITLE)
        return TITLE

    context.user_data.setdefault("sell_draft", {})["title"] = title

    await _reply_sell_prompt(message, context,
        "သက်ဆိုင်ရာ Major ကို ရွေးချယ်ပါ။",
        reply_markup=_major_keyboard(),
    )
    await _save_sell_draft(update, context, MAJOR)
    return MAJOR


async def receive_major(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query

    if query is None or not query.data:
        return MAJOR

    slug = query.data.removeprefix("sell:major:")

    if slug not in MAJORS:
        await query.answer(
            "Major မမှန်ကန်ပါ။",
            show_alert=True,
        )
        return MAJOR

    draft = context.user_data.setdefault("sell_draft", {})

    draft["major"] = MAJORS[slug]
    draft["major_slug"] = slug

    await query.answer()

    await _edit_sell_prompt(query, context,
        "📖 ဘယ်နှစ် Year လဲ။ အောက်မှာ ရွေးချယ်ပါ။",
        reply_markup=_year_keyboard(),
    )
    await _save_sell_draft(update, context, YEAR)
    return YEAR


async def receive_year_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query

    if query is None or not query.data:
        return YEAR

    try:
        year = int(query.data.removeprefix("sell:year:"))

    except ValueError:
        year = 0

    if not 1 <= year <= 6:
        await query.answer(
            "Year မမှန်ကန်ပါ။",
            show_alert=True,
        )
        return YEAR

    draft = context.user_data.setdefault("sell_draft", {})
    draft["year"] = year
    draft.pop("semester", None)

    await query.answer()

    await _edit_sell_prompt(query, context,
        "📑 ဘယ် Semester အတွက်လဲ။",
        reply_markup=_semester_keyboard(year),
    )
    await _save_sell_draft(update, context, SEMESTER)
    return SEMESTER


async def receive_year_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Keep numeric text input available for users who prefer typing."""

    message = update.effective_message

    raw = (message.text or "").strip() if message else ""

    try:
        year = int(raw)

    except ValueError:
        year = 0

    if not 1 <= year <= 6:
        await _reply_sell_prompt(message, context,
            "Year ကို 1 မှ 6 အတွင်း ရွေးပါ။",
            reply_markup=_year_keyboard(),
        )
        await _save_sell_draft(update, context, YEAR)
        return YEAR

    draft = context.user_data.setdefault("sell_draft", {})
    draft["year"] = year
    draft.pop("semester", None)

    await _reply_sell_prompt(message, context,
        "📑 ဘယ် Semester အတွက်လဲ။",
        reply_markup=_semester_keyboard(year),
    )
    await _save_sell_draft(update, context, SEMESTER)
    return SEMESTER


async def receive_semester_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query

    if query is None or not query.data:
        return SEMESTER

    value = query.data.removeprefix("sell:semester:")
    draft = context.user_data.setdefault("sell_draft", {})
    year = draft.get("year")
    first, second, both_value = _semester_values(year)
    semester_map = {
        str(first): first,
        str(second): second,
        "both": both_value,
    }

    if value not in semester_map:
        await query.answer(
            "Semester မမှန်ကန်ပါ။",
            show_alert=True,
        )
        return SEMESTER

    draft["semester"] = semester_map[value]

    await query.answer()

    await _edit_sell_prompt(query, context,
        _price_prompt(),
        reply_markup=_cancel_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    await _save_sell_draft(update, context, PRICE)
    return PRICE


async def receive_semester_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Accept legacy numeric input while offering the new inline choices."""

    message = update.effective_message

    raw = (message.text or "").strip().lower() if message else ""
    draft = context.user_data.setdefault("sell_draft", {})
    first, second, both_value = _semester_values(draft.get("year"))
    semester_map = {
        str(first): first,
        str(second): second,
        "both": both_value,
        f"{first}&{second}": both_value,
        f"{first} & {second}": both_value,
        "နှစ်ခုလုံး": both_value,
    }

    if raw not in semester_map:
        await _reply_sell_prompt(message, context,
            "Semester ကို အောက်က Button များမှ ရွေးချယ်ပါ။",
            reply_markup=_semester_keyboard(draft.get("year")),
        )
        await _save_sell_draft(update, context, SEMESTER)
        return SEMESTER

    draft["semester"] = semester_map[raw]

    await _reply_sell_prompt(message, context,
        _price_prompt(),
        reply_markup=_cancel_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    await _save_sell_draft(update, context, PRICE)
    return PRICE


async def receive_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    message = update.effective_message

    raw = (
        (message.text or "").strip().lower().replace(",", "")
        if message
        else ""
    )

    draft = context.user_data.setdefault("sell_draft", {})

    if raw in {
        "negotiable",
        "ညှိနှိုင်း",
        "ဈေးညှိနှိုင်း",
    }:

        draft["is_negotiable"] = True
        draft["price"] = None

    else:
        try:
            price = float(raw)

            if price <= 0 or price > 1_000_000_000:
                raise ValueError

        except ValueError:
            await _reply_sell_prompt(message, context,
                "ဈေးနှုန်းကို အပေါင်းဂဏန်းနဲ့ ထည့်ပါ၊ "
                "သို့မဟုတ် negotiable လို့ ရိုက်ပါ။",
                reply_markup=_cancel_keyboard(),
            )
            await _save_sell_draft(update, context, PRICE)
            return PRICE

        draft["is_negotiable"] = False

        draft["price"] = (
            int(price) if price.is_integer() else price
        )

    await _reply_sell_prompt(message, context,
        "စာအုပ်အခြေအနေကို ဖော်ပြပေးပါ။ (ဥပမာ New, Good, Used)",
        reply_markup=_cancel_keyboard(),
    )
    await _save_sell_draft(update, context, CONDITION)
    return CONDITION


async def receive_condition(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    message = update.effective_message

    condition = (
        (message.text or "").strip()
        if message
        else ""
    )

    if not condition or len(condition) > 250:
        await _reply_sell_prompt(message, context,
            "အခြေအနေကို စာလုံး ၁ မှ ၂၅၀ အတွင်း ထည့်ပါ။",
            reply_markup=_cancel_keyboard(),
        )
        await _save_sell_draft(update, context, CONDITION)
        return CONDITION

    context.user_data.setdefault(
        "sell_draft",
        {},
    )["condition"] = condition

    await _reply_sell_prompt(message, context,
        "📸 စာအုပ်ပုံကို အများဆုံး ၄ ပုံအထိ ပို့ပေးပါ။\n"
        "ပုံ ၁ ပုံ သို့မဟုတ် အများဆုံး ၄ ပုံ ပို့ပြီးရင် "
        "<b>ဓာတ်ပုံပြီးပါပြီ</b> ကို နှိပ်ပါ။",
        reply_markup=_cancel_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    await _save_sell_draft(update, context, PHOTO)
    return PHOTO


async def receive_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    message = update.effective_message

    if message is None or not message.photo:
        if message:
            await _reply_sell_prompt(message, context,
                "ဓာတ်ပုံတစ်ပုံ ပို့ပေးပါ။",
                reply_markup=_cancel_keyboard(),
            )
            await _save_sell_draft(update, context, PHOTO)

        return PHOTO

    draft = context.user_data.setdefault("sell_draft", {})

    photo_file_ids = draft.setdefault(
        "photo_file_ids",
        [],
    )

    file_id = message.photo[-1].file_id

    if file_id not in photo_file_ids:

        if len(photo_file_ids) >= MAX_PHOTOS:

            notice = await _reply_sell_prompt(message, context,
                "ဓာတ်ပုံ ၄ ပုံ ပြည့်သွားပါပြီ။ "
                "✅ ဓာတ်ပုံပြီးပါပြီ ကို နှိပ်ပြီး Listing တင်ပါ။",
                reply_markup=_photo_keyboard(),
            )

            draft.setdefault(
                "photo_notice_message_ids",
                [],
            ).append(notice.message_id)
            await _save_sell_draft(update, context, PHOTO)
            return PHOTO

        photo_file_ids.append(file_id)

    count = len(photo_file_ids)

    if count >= MAX_PHOTOS:

        text = (
            "✅ ဓာတ်ပုံ ၄ ပုံ ပြည့်ပါပြီ။ "
            "Listing တင်ရန် အောက်က Button ကို နှိပ်ပါ။"
        )

    else:

        text = (
            f"✅ ဓာတ်ပုံ {count}/{MAX_PHOTOS} ပုံ ရရှိပါပြီ။\n"
            "နောက်ထပ်ပုံ ပို့နိုင်သေးတယ်။ "
            "ပြီးသွားရင် <b>ဓာတ်ပုံပြီးပါပြီ</b> ကို နှိပ်ပါ။"
        )

    notice = await _reply_sell_prompt(message, context,
        text,
        reply_markup=_photo_keyboard(),
        parse_mode=ParseMode.HTML,
    )

    # Save every temporary photo notice message ID.
    # These messages will all be deleted when the seller confirms or cancels.
    draft.setdefault(
        "photo_notice_message_ids",
        [],
    ).append(notice.message_id)
    await _save_sell_draft(update, context, PHOTO)
    return PHOTO


async def delete_photo_notices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Backward-compatible wrapper; final cleanup removes all sell prompts."""
    await _cleanup_sell_prompts(update, context)


async def publish_listing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    user = update.effective_user
    chat = update.effective_chat

    if user is None or chat is None:
        await _cleanup_sell_prompts(update, context)
        await _delete_sell_draft(user.id if user else None)
        context.user_data.pop("sell_draft", None)
        return ConversationHandler.END

    chat_id = chat.id

    draft = context.user_data.get("sell_draft") or {}

    photo_file_ids = list(
        dict.fromkeys(
            draft.get("photo_file_ids") or []
        )
    )[:MAX_PHOTOS]

    if not photo_file_ids:

        if update.callback_query:
            await update.callback_query.answer(
                "အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ ပို့ပေးပါ။",
                show_alert=True,
            )

        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ ပို့ပေးပါ။",
                reply_markup=_cancel_keyboard(),
            )

        return PHOTO

    if update.callback_query:
        await update.callback_query.answer()

    required = {
        "title",
        "major",
        "year",
        "semester",
        "condition",
        "is_negotiable",
    }

    if not required.issubset(draft):

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "အချက်အလက်အချို့ ပျောက်နေပါတယ်။ "
                "/sell နဲ့ ပြန်စတင်ပေးပါ။"
            ),
        )

        await _cleanup_sell_prompts(update, context)
        await _delete_sell_draft(user.id)
        context.user_data.pop("sell_draft", None)
        return ConversationHandler.END

    now = datetime.now(timezone.utc)

    book_id = ObjectId()

    book = {
        "_id": book_id,
        "title": draft["title"],
        "major": draft["major"],
        "major_slug": draft.get("major_slug"),
        "year": draft["year"],
        "semester": draft["semester"],
        "price": draft.get("price"),
        "is_negotiable": draft["is_negotiable"],
        "condition": draft["condition"],
        "photo_file_id": photo_file_ids[0],
        "photo_file_ids": photo_file_ids,
        "seller_id": user.id,
        "seller_username": user.username,
        "status": "Available",
        "admin_hidden": False,
        "current_buyer_id": None,
        "created_at": now,
        "updated_at": now,
    }

    db = get_database()

    try:
        await db.books.insert_one(book)

    except PyMongoError:
        logger.exception(
            "Could not save new book listing for seller %s",
            user.id,
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text="စာအုပ်အချက်အလက် သိမ်းဆည်းရာမှာ အမှားဖြစ်သွားပါတယ်။",
        )
        await _cleanup_sell_prompts(update, context)
        await _delete_sell_draft(user.id)
        context.user_data.pop("sell_draft", None)
        return ConversationHandler.END

    if not settings.channel_id:

        await db.books.update_one(
            {"_id": book_id},
            {"$set": {"channel_sync_error": True}},
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ စာအုပ်အချက်အလက်ကို သိမ်းပြီးပါပြီ။\n"
                "⚠️ CHANNEL_ID မသတ်မှတ်ထားတဲ့အတွက် "
                "Channel မှာ မတင်နိုင်သေးပါဘူး။ Admin ကို ဆက်သွယ်ပါ။"
            ),
        )
        await _cleanup_sell_prompts(update, context)
        await _delete_sell_draft(user.id)
        context.user_data.pop("sell_draft", None)
        return ConversationHandler.END

    channel_id = normalize_chat_id(settings.channel_id)

    published_message_ids: list[int] = []

    try:

        if len(photo_file_ids) == 1:

            posted = await context.bot.send_photo(
                chat_id=channel_id,
                photo=photo_file_ids[0],
                caption=build_book_caption(book),
                reply_markup=purchase_keyboard(
                    str(book_id),
                    "Available",
                ),
            )

            channel_message_id = posted.message_id

            published_message_ids.append(
                posted.message_id
            )

            channel_post_type = "photo"

            channel_photo_message_ids = [
                posted.message_id
            ]

        else:

            media = [
                InputMediaPhoto(media=file_id)
                for file_id in photo_file_ids
            ]

            media_messages = await context.bot.send_media_group(
                chat_id=channel_id,
                media=media,
            )

            published_message_ids.extend(
                item.message_id
                for item in media_messages
            )

            # Telegram does not support inline keyboards on media groups.
            # Publish the listing details and actions as the next message.
            action_post = await context.bot.send_message(
                chat_id=channel_id,
                text=build_book_caption(book),
                reply_markup=purchase_keyboard(
                    str(book_id),
                    "Available",
                ),
            )

            channel_message_id = action_post.message_id

            published_message_ids.append(
                action_post.message_id
            )

            channel_post_type = "text"

            channel_photo_message_ids = [
                item.message_id
                for item in media_messages
            ]

        await db.books.update_one(
            {"_id": book_id},
            {
                "$set": {
                    "channel_id": settings.channel_id,
                    "channel_message_id": channel_message_id,
                    "channel_post_type": channel_post_type,
                    "channel_photo_message_ids": channel_photo_message_ids,
                    "channel_sync_error": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    except (TelegramError, PyMongoError):

        logger.exception(
            "Could not publish book %s to the listing channel",
            book_id,
        )

        # Remove partially published messages.
        for published_message_id in published_message_ids:

            try:
                await context.bot.delete_message(
                    channel_id,
                    published_message_id,
                )

            except TelegramError:
                logger.warning(
                    "Could not remove incomplete listing message %s",
                    published_message_id,
                )

        await db.books.update_one(
            {"_id": book_id},
            {"$set": {"channel_sync_error": True}},
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ စာအုပ်အချက်အလက်ကို သိမ်းပြီးပါပြီ။\n"
                "⚠️ Channel မှာ တင်ရာမှာ အမှားဖြစ်သွားလို့ "
                "Admin ကို အသိပေးထားပါ။"
            ),
        )

    else:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ စာအုပ်ကို Channel မှာ တင်ပြီးပါပြီ။ "
                f"(ဓာတ်ပုံ {len(photo_file_ids)} ပုံ)"
            ),
        )

    await _cleanup_sell_prompts(update, context)
    await _delete_sell_draft(user.id)
    context.user_data.pop("sell_draft", None)
    return ConversationHandler.END


async def finish_photos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query

    if query is None:
        return PHOTO

    return await publish_listing(update, context)


async def cancel_sell(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    # Delete only prompts posted by the bot; seller messages remain untouched.
    await _cleanup_sell_prompts(update, context)
    await _delete_sell_draft(update.effective_user.id if update.effective_user else None)
    context.user_data.pop("sell_draft", None)

    if update.callback_query:

        await update.callback_query.answer(
            "စာအုပ်တင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။"
        )

        if update.effective_chat:

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ စာအုပ်တင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။",
            )

    elif update.effective_message:

        await update.effective_message.reply_text("❌ စာအုပ်တင်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")

    return ConversationHandler.END


def build_sell_handler() -> ConversationHandler:

    return ConversationHandler(
        entry_points=[
            CommandHandler("sell", start_sell),
            CallbackQueryHandler(
                start_sell,
                pattern=r"^menu:sell$",
            ),
        ],

        states={
            TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_title,
                )
            ],

            MAJOR: [
                CallbackQueryHandler(
                    receive_major,
                    pattern=r"^sell:major:",
                )
            ],

            YEAR: [
                CallbackQueryHandler(
                    receive_year_callback,
                    pattern=r"^sell:year:",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_year_text,
                ),
            ],

            SEMESTER: [
                CallbackQueryHandler(
                    receive_semester_callback,
                    pattern=r"^sell:semester:",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_semester_text,
                ),
            ],

            PRICE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_price,
                )
            ],

            CONDITION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_condition,
                )
            ],

            PHOTO: [
                CallbackQueryHandler(
                    finish_photos,
                    pattern=r"^sell:photos:done$",
                ),
                MessageHandler(
                    filters.PHOTO,
                    receive_photo,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    invalid_photo,
                ),
            ],
        },

        fallbacks=[
            CommandHandler("cancel", cancel_sell),
            CallbackQueryHandler(
                cancel_sell,
                pattern=r"^sell:cancel$",
            ),
        ],

        # Keep the active Sell conversation and its user_data draft on disk.
        # This lets the seller continue after a graceful PM2 restart.
        name="sell_conversation",
        persistent=True,
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )


async def invalid_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    if update.effective_message:

        has_photos = bool(
            context.user_data.get("sell_draft", {}).get("photo_file_ids")
        )

        await _reply_sell_prompt(update.effective_message, context,
            "စာအုပ်ပုံကို Photo အနေနဲ့ ပို့ပေးပါ။",
            reply_markup=(
                _photo_keyboard()
                if has_photos
                else _cancel_keyboard()
            ),
        )
        await _save_sell_draft(update, context, PHOTO)

    return PHOTO

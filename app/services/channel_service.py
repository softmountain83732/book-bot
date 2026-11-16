"""Helpers for publishing and synchronizing marketplace listings in a channel."""
from telegram import Bot, InputMediaPhoto

from app.keyboards.book_actions import purchase_keyboard


def normalize_chat_id(value: str | int) -> str | int:
    """Convert numeric Telegram chat IDs to integers."""
    if isinstance(value, int):
        return value

    value = str(value).strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def format_semester(year, semester) -> str:
    """Return the semester label for the current university year structure.

    Year 2 moved from the old 1/2 labels to 3/4. Older Year 2 records are
    still stored with 1, 2, or Both, so those legacy values are interpreted
    as 3, 4, and 3 & 4 respectively. Other years retain 1/2.
    """
    year_is_two = str(year).strip() == "2"
    raw = str(semester if semester is not None else "N/A").strip()
    if not raw:
        return "N/A"

    normalized = raw.lower().replace("(နှစ်ခုလုံး)", "").strip()
    compact = "".join(normalized.split())

    both_values = {"both", "1&2", "3&4"}
    if compact in both_values:
        label = "3 & 4" if year_is_two else "1 & 2"
        return f"{label} (နှစ်ခုလုံး)"

    if year_is_two:
        # Backward compatibility for existing Year 2 listings.
        if compact == "1":
            return "3"
        if compact == "2":
            return "4"
    else:
        if compact == "1":
            return "1"
        if compact == "2":
            return "2"

    return raw


def build_book_caption(book: dict) -> str:
    """Build the public text/caption for a book listing."""
    price = book.get("price")
    if book.get("is_negotiable"):
        price_text = "ဈေးညှိနှိုင်း"
    elif isinstance(price, (int, float)):
        price_text = f"{price:,.0f} MMK"
    else:
        price_text = "ဈေးနှုန်း မသတ်မှတ်ထားပါ"

    semester = format_semester(book.get("year"), book.get("semester", "N/A"))

    caption = (
        f'📚 {book.get("title", "Untitled")}\n\n'
        f'🎓 Major: {book.get("major", "N/A")}\n'
        f'📖 Year: {book.get("year", "N/A")}\n'
        f'📑 Semester: {semester}\n'
        f"💰 ဈေးနှုန်း: {price_text}\n"
        f'📝 အခြေအနေ: {book.get("condition", "N/A")}\n\n'
        f'🆔 Book ID: {book["_id"]}'
    )

    status = book.get("status", "Available")
    if status == "Pending":
        caption += "\n\n⏳ ဒီစာအုပ်ကို ဝယ်ယူရန် ညှိနှိုင်းနေဆဲ ဖြစ်ပါသည်။"
    elif status == "Sold":
        caption += "\n\n❌ ရောင်းထွက်သွားပါပြီ (Sold Out)"
    elif status == "Cancelled":
        if book.get("admin_hidden"):
            caption += "\n\n🚫 Admin မှ ဒီ Listing ကို ဖယ်ရှားထားပါသည်။"
        else:
            caption += "\n\n🗑️ ရောင်းသူမှ ရောင်းချမှုကို ပယ်ဖျက်လိုက်ပါသည်။"
    elif status == "Delisted":
        caption += "\n\n⏸️ ရောင်းသူမှ ယာယီ Delist လုပ်ထားသော Listing ဖြစ်ပါသည်။"
    elif status == "Deleted":
        caption += "\n\n🗑️ ဒီ Listing ကို ရောင်းသူမှ ဖယ်ရှားထားပါသည်။"

    return caption


async def update_book_channel(
    bot: Bot,
    book: dict,
    status: str | None = None,
    update_photo: bool = False,
) -> None:
    """Update a listing's channel text/caption and inline buttons.

    Older listings and single-photo listings use a photo message with a
    caption. Multi-photo listings use an album followed by a separate text
    message carrying the listing details and inline buttons.
    """
    message_id = book.get("channel_message_id")
    channel_id = book.get("channel_id")
    if not message_id or not channel_id:
        raise ValueError(f"Book {book.get('_id')} has no channel post reference.")

    updated_book = dict(book)
    if status is not None:
        updated_book["status"] = status

    keyboard = purchase_keyboard(
        book_id=str(updated_book["_id"]),
        status=updated_book.get("status", "Available"),
    )
    normalized_channel_id = normalize_chat_id(channel_id)
    caption = build_book_caption(updated_book)
    post_type = updated_book.get("channel_post_type", "photo")

    if post_type == "text":
        if update_photo:
            photo_message_ids = updated_book.get("channel_photo_message_ids") or []
            photo_file_ids = updated_book.get("photo_file_ids") or []
            if not photo_message_ids or not photo_file_ids:
                raise ValueError(f"Book {updated_book.get('_id')} has no editable channel photo.")
            await bot.edit_message_media(
                chat_id=normalized_channel_id,
                message_id=int(photo_message_ids[0]),
                media=InputMediaPhoto(media=photo_file_ids[0]),
            )
        await bot.edit_message_text(
            chat_id=normalized_channel_id,
            message_id=int(message_id),
            text=caption,
            reply_markup=keyboard,
        )
        return

    if update_photo:
        photo_file_id = updated_book.get("photo_file_id")
        if not photo_file_id:
            raise ValueError(f"Book {updated_book.get('_id')} has no photo_file_id.")
        await bot.edit_message_media(
            chat_id=normalized_channel_id,
            message_id=int(message_id),
            media=InputMediaPhoto(media=photo_file_id, caption=caption),
            reply_markup=keyboard,
        )
    else:
        await bot.edit_message_caption(
            chat_id=normalized_channel_id,
            message_id=int(message_id),
            caption=caption,
            reply_markup=keyboard,
        )

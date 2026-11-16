"""Keyboard builders used by the Favorites handler."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

PAGE_SIZE = 5


def favorites_list_keyboard(books: list[dict], offset: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for book in books:
        book_id = str(book.get("_id"))
        title = str(book.get("title", "Untitled"))
        if len(title) > 42:
            title = title[:39] + "..."
        rows.append([
            InlineKeyboardButton(
                f"📚 {title}",
                callback_data=f"favorites:book:{book_id}:{offset}",
            )
        ])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️ ယခင်", callback_data=f"favorites:list:{max(0, offset - PAGE_SIZE)}"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("နောက်တစ်မျက်နှာ ➡️", callback_data=f"favorites:list:{offset + PAGE_SIZE}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="favorites:exit")])
    return InlineKeyboardMarkup(rows)


def favorite_book_detail_keyboard(book_id: str, offset: int, available: bool) -> InlineKeyboardMarkup:
    rows = []
    if available:
        rows.append([InlineKeyboardButton("📖 ဝယ်ယူရန်", callback_data=f"buy:{book_id}")])
    rows.append([InlineKeyboardButton("🗑️ Favorites မှ ဖယ်ရှားမည်", callback_data=f"favorites:remove:{book_id}:{offset}")])
    rows.append([InlineKeyboardButton("⬅️ Favorites စာရင်း", callback_data=f"favorites:list:{offset}")])
    return InlineKeyboardMarkup(rows)

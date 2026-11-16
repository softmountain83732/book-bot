"""Inline actions attached to public book listings."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def buyer_cancel_keyboard(request_id: str) -> InlineKeyboardMarkup:
    """Show the buyer a guarded cancel action for their pending request."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ ဝယ်ယူမှု Request ကို Cancel လုပ်ရန်", callback_data=f"purchase:cancel:ask:{request_id}")
    ]])


def purchase_keyboard(book_id: str, status: str) -> InlineKeyboardMarkup | None:
    """Build callback-based Buy/Favorite/Report buttons for a listing.

    Callback buttons are intentional: URL deep links reopen /start and show
    the main menu before the requested action can run.
    """
    if status == "Available":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 ဝယ်ယူရန်", callback_data=f"buy:{book_id}")],
            [
                InlineKeyboardButton("❤️ သိမ်းထားမည်", callback_data=f"favorite:add:{book_id}"),
                InlineKeyboardButton("🚩 Report", callback_data=f"report:book:{book_id}"),
            ],
        ])

    if status == "Pending":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⏳ ညှိနှိုင်းနေဆဲ", callback_data=f"buy:{book_id}")],
            [InlineKeyboardButton("🚩 Report", callback_data=f"report:book:{book_id}")],
        ])

    if status == "Delisted":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ ယာယီရောင်းချမှု ရပ်နားထားသည်", callback_data="browse:noop")],
            [
                InlineKeyboardButton("❤️ သိမ်းထားမည်", callback_data=f"favorite:add:{book_id}"),
                InlineKeyboardButton("🚩 Report", callback_data=f"report:book:{book_id}"),
            ],
        ])

    return None


def seller_control_keyboard(book_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ရောင်းထွက်သွားပြီ", callback_data=f"seller:sold:{book_id}")],
        [InlineKeyboardButton("⚠️ ဝယ်သူ ပျောက်သွားသည်", callback_data=f"seller:lost:{book_id}")],
        [InlineKeyboardButton("🗑️ မရောင်းတော့ပါ", callback_data=f"seller:cancel:{book_id}")],
    ])

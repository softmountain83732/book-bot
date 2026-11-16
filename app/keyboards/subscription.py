"""Channel subscription prompt keyboard."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings


def subscription_prompt_text() -> str:
    return (
        "🔒 <b>Bot ကို အသုံးပြုရန် Channel Join လုပ်ပေးပါ။</b>\n\n"
        "Channel ကို Join လုပ်ပြီးပါက အောက်က <b>စစ်ဆေးမည်</b> ကို နှိပ်ပါ။"
    )


def subscription_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if settings.channel_join_url:
        rows.append([
            InlineKeyboardButton(
                "📢 Channel Join လုပ်ရန်",
                url=settings.channel_join_url,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            "✅ Join ပြီးပါပြီ · စစ်ဆေးမည်",
            callback_data="join:check",
        )
    ])
    return InlineKeyboardMarkup(rows)

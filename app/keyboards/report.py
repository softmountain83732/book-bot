"""Reason selection keyboard for user-submitted listing reports."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

REPORT_REASONS = {
    "misleading_info": "အချက်အလက် မမှန်ကန်ခြင်း",
    "wrong_price": "ဈေးနှုန်း မမှန်ကန်ခြင်း",
    "duplicate": "ထပ်နေသော Listing",
    "scam": "လိမ်လည်မှု သံသယရှိခြင်း",
    "inappropriate": "မသင့်လျော်သော အကြောင်းအရာ",
    "other": "အခြားအကြောင်းရင်း",
}


def report_reason_keyboard(book_id: str) -> InlineKeyboardMarkup:
    rows = []
    for code, label in REPORT_REASONS.items():
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=f"report:reason:{book_id}:{code}",
            )
        ])
    rows.append([
        InlineKeyboardButton("❌ ပယ်ဖျက်မည်", callback_data=f"report:cancel:{book_id}"),
    ])
    return InlineKeyboardMarkup(rows)

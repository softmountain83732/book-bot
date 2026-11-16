from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def pending_decision_keyboard(book_id: str) -> InlineKeyboardMarkup:
    """Seller decisions requested when a purchase has been Pending for 24 hours."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤝 ဆက်လက်ညှိနှိုင်းမည်",
                    callback_data=f"seller:continue:{book_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "↩️ Listing ကို ပြန်ဖွင့်မည်",
                    callback_data=f"seller:release:{book_id}",
                )
            ],
        ]
    )

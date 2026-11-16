"""Main user menu keyboards."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 စာအုပ်ရှာရန်", callback_data="menu:browse"),
            InlineKeyboardButton("📤 စာအုပ်ရောင်းရန်", callback_data="menu:sell"),
        ],
        [
            InlineKeyboardButton("📖 ကျွန်ုပ်၏စာအုပ်များ", callback_data="menu:my_books"),
            InlineKeyboardButton("❤️ Favorites", callback_data="menu:favorites"),
        ],
        [
            InlineKeyboardButton("ℹ️ အကူအညီ", callback_data="menu:help"),
        ],
    ])

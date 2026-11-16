"""Start command, deep-link continuation and main-menu callbacks."""
import logging
from html import escape

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.keyboards.main_menu import get_main_menu
from app.keyboards.subscription import subscription_keyboard, subscription_prompt_text
from app.services.deep_link_service import perform_start_action
from app.services.subscription_service import is_user_subscribed
from app.services.user_service import register_user

logger = logging.getLogger(__name__)


def welcome_text(first_name: str | None) -> str:
    safe_name = escape(first_name or "မိတ်ဆွေ")
    return (
        f"<b> မင်္ဂလာပါ {safe_name}</b>\n\n"
        "<b>HBTU Book Marketplace</b> မှ ကြိုဆိုပါတယ်။\n"
        "စာအုပ်ဝယ်ယူခြင်း၊ ရောင်းချခြင်းနဲ့ ရှာဖွေခြင်းတို့အတွက် အောက်ပါ Menu ကိုအသုံးပြနိုင်ပါတယ်။"
    )


async def _continue_action(message, context: ContextTypes.DEFAULT_TYPE, user, payload: str) -> None:
    try:
        text, show_alert, send_feedback = await perform_start_action(
            bot=context.bot,
            user=user,
            payload=payload,
            user_data=context.user_data,
        )
        if send_feedback:
            await message.reply_text(text)
    except Exception:
        logger.exception("Could not continue deep-link action '%s' for user %s", payload, user.id)
        await message.reply_text("ဒီလုပ်ဆောင်ချက်ကို ဆက်လုပ်ရာမှာ အမှားဖြစ်သွားပါတယ်။ နောက်တစ်ကြိမ် ပြန်ကြိုးစားပါ။")


async def show_main_menu(message, user) -> None:
    await register_user(user)
    await message.reply_text(
        welcome_text(user.first_name),
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    payload = context.args[0].strip() if context.args else None
    if payload:
        context.user_data["pending_start_action"] = payload

    if not await is_user_subscribed(context.bot, user.id):
        await message.reply_text(
            subscription_prompt_text(),
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )
        return

    await register_user(user)
    await message.reply_text(
        welcome_text(user.first_name),
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )

    pending = context.user_data.pop("pending_start_action", None)
    if pending:
        await _continue_action(message, context, user, pending)


async def join_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    if not await is_user_subscribed(context.bot, user.id):
        await query.answer("Channel ကို Join လုပ်ထားကြောင်း မတွေ့သေးပါ။", show_alert=True)
        try:
            await query.edit_message_text(
                subscription_prompt_text(),
                reply_markup=subscription_keyboard(),
                parse_mode="HTML",
            )
        except TelegramError:
            pass
        return

    await query.answer("Channel Join စစ်ဆေးပြီးပါပြီ။")
    await register_user(user)
    try:
        await query.edit_message_text(
            welcome_text(user.first_name),
            reply_markup=get_main_menu(),
            parse_mode="HTML",
        )
    except TelegramError:
        if query.message:
            await query.message.reply_text(
                welcome_text(user.first_name),
                reply_markup=get_main_menu(),
                parse_mode="HTML",
            )

    pending = context.user_data.pop("pending_start_action", None)
    if pending and query.message:
        await _continue_action(query.message, context, user, pending)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    if query.data == "menu:help":
        text = (
            "ℹ️ <b>အကူအညီ</b>\n\n"
            "/sell — စာအုပ်ရောင်းရန်\n"
            "/browse — စာအုပ်ရှာရန်\n"
            "/mybooks — ကိုယ်တင်ထားသောစာအုပ်များ\n"
            "/favorites — သိမ်းထားသောစာအုပ်များ\n"
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
        return
    if query.data in ("menu:home", "menu:main"):
        await query.edit_message_text(
            "🎓 <b>University Book Marketplace</b>\n\nလုပ်ဆောင်လိုသော Menu ကို ရွေးချယ်ပါ။",
            reply_markup=get_main_menu(),
            parse_mode="HTML",
        )


def register_start_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(
        CallbackQueryHandler(join_check_callback, pattern=r"^join:check$")
    )
    application.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern=r"^menu:(?!sell$|browse$|my_books$|favorites$|admin$)",
        )
    )

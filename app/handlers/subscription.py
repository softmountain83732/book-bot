"""Global channel-membership gate for private marketplace interactions."""
from telegram import Update
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes, TypeHandler

from app.keyboards.subscription import subscription_keyboard, subscription_prompt_text
from app.services.subscription_service import is_user_subscribed


async def _subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != "private":
        return

    # /start must run so it can show the join prompt and preserve deep-link payloads.
    message = update.effective_message
    if message and message.text:
        command = message.text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if command == "/start":
            return

    query = update.callback_query
    if query and query.data == "join:check":
        return

    if await is_user_subscribed(context.bot, user.id):
        return

    if query:
        await query.answer("Bot ကို အသုံးပြုရန် Channel Join လုပ်ပေးပါ။", show_alert=True)
        try:
            await query.message.reply_text(
                subscription_prompt_text(),
                reply_markup=subscription_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
    elif message:
        await message.reply_text(
            subscription_prompt_text(),
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )

    raise ApplicationHandlerStop


def register_subscription_gate(application: Application) -> None:
    """Register the gate in group -1 so it runs before feature handlers."""
    application.add_handler(TypeHandler(Update, _subscription_gate), group=-1)

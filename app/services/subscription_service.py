"""Telegram channel membership checks."""
import logging

from telegram.error import TelegramError

from app.config import settings

logger = logging.getLogger(__name__)


async def is_user_subscribed(bot, user_id: int) -> bool:
    """Return True when a user can access the configured private channel."""
    if not settings.channel_id:
        # Allows local development without a required channel configured.
        logger.warning("CHANNEL_ID is empty; subscription gate is disabled.")
        return True
    try:
        member = await bot.get_chat_member(settings.channel_id, user_id)
    except TelegramError:
        logger.exception(
            "Could not check channel membership for user %s. Ensure the bot is an admin in the channel.",
            user_id,
        )
        return False

    status = getattr(member, "status", "left")
    if status in ("creator", "administrator", "member"):
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False

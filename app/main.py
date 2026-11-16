import asyncio
import logging
import shutil
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    PicklePersistence,
)

from app.config import settings
from app.database.mongo import connect_db, close_db
from app.database.indexes import create_indexes
from app.services.audit_service import ensure_audit_indexes

from app.handlers.subscription import register_subscription_gate
from app.handlers.start import register_start_handlers
from app.handlers.sell import build_sell_handler
from app.handlers.my_books import register_my_books_handler
from app.handlers.browse import register_browse_handlers
from app.handlers.favorites import register_favorites_handlers
from app.handlers.purchase import build_purchase_handler
from app.handlers.seller_control import build_seller_control_handler
from app.handlers.reports import register_report_handlers
from app.handlers.admin import register_admin_handlers
from app.handlers.admin_reports import register_admin_reports_handlers
from app.handlers.admin_pending import register_admin_pending_handlers
from app.handlers.admin_audit import register_admin_audit_handlers
from app.services.pending_lifecycle_service import pending_lifecycle_loop


# Keep PTB state in the project-root data directory. Migrate the earlier
# app/data path once so an existing persistence file is not abandoned.
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
PERSISTENCE_DIR = PROJECT_ROOT / "data"
PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)
PERSISTENCE_FILE = PERSISTENCE_DIR / "bot_state.pickle"
LEGACY_PERSISTENCE_FILE = APP_DIR / "data" / "bot_state.pickle"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

if not PERSISTENCE_FILE.exists() and LEGACY_PERSISTENCE_FILE.exists():
    try:
        shutil.copy2(LEGACY_PERSISTENCE_FILE, PERSISTENCE_FILE)
        logger.info("Migrated PTB persistence file to %s", PERSISTENCE_FILE)
    except OSError:
        logger.exception("Could not migrate legacy PTB persistence file")

persistence = PicklePersistence(
    filepath=str(PERSISTENCE_FILE),
    update_interval=1.0,
)


async def post_init(application: Application) -> None:
    """Connect MongoDB, initialize indexes, and start lifecycle monitoring."""

    db = await connect_db()

    try:
        await create_indexes(db)
        await ensure_audit_indexes(db)
        logger.info("Database initialization completed.")
    except Exception:
        logger.exception("Database initialization failed.")
        await close_db()
        raise

    # Run the Pending purchase lifecycle worker in the same event loop.
    # It handles 22-hour reminders, 24-hour seller decisions and 48-hour
    # admin escalation without requiring JobQueue/APScheduler dependencies.
    task = asyncio.create_task(
        pending_lifecycle_loop(application),
        name="pending-purchase-lifecycle",
    )
    application.bot_data["pending_lifecycle_task"] = task
    logger.info("Pending purchase lifecycle worker started.")
    logger.info("PTB persistence file: %s (exists=%s)", PERSISTENCE_FILE, PERSISTENCE_FILE.exists())


async def post_shutdown(application: Application) -> None:
    """Stop lifecycle monitoring and close MongoDB cleanly."""

    task = application.bot_data.pop("pending_lifecycle_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await close_db()
    logger.info("Application shutdown completed.")


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message

    if message is None:
        return

    await message.reply_text(
        "📚 University Book Marketplace Bot\n\n"
        "/start - Main Menu\n"
        "/sell - စာအုပ်ရောင်းရန်\n"
        "/browse - စာအုပ်ရှာဖွေရန်\n"
        "/favorites - သိမ်းထားသောစာအုပ်များ\n"
        "/admin - Admin Dashboard\n"
        "/adminpending - Pending Purchase Queue (Admin)\n"
        "/adminaudit - Marketplace Activity Log (Admin)\n"
        "/help - အကူအညီ\n"
        "/cancel - လက်ရှိလုပ်ဆောင်ချက်ကို ပယ်ဖျက်ရန်"
    )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.error(
        "Unhandled exception while processing Telegram update.",
        exc_info=context.error,
    )


def main() -> None:
    logger.info("Initializing University Book Marketplace Bot...")
    logger.info("PTB persistence file: %s (exists=%s)", PERSISTENCE_FILE, PERSISTENCE_FILE.exists())

    application = (
        Application.builder()
        .token(settings.bot_token)
        .persistence(persistence)
        .concurrent_updates(False)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # 1. Enforce channel membership before marketplace handlers.
    register_subscription_gate(application)

    # 2. Start command, join verification and general menu.
    register_start_handlers(application)

    # 3. Seller listing conversation.
    application.add_handler(
        build_sell_handler()
    )

    # 4. Seller's own listings and listing editor.
    register_my_books_handler(application)

    # 5. Browse, title search, filters and pagination.
    register_browse_handlers(application)

    # 6. Favorites and saved books.
    register_favorites_handlers(application)

    # 7. Buyer purchase callbacks.
    application.add_handler(
        build_purchase_handler()
    )

    # 8. Seller transaction controls.
    application.add_handler(
        build_seller_control_handler()
    )

    # 9. User listing reports.
    register_report_handlers(application)

    # 10. Main administrator dashboard.
    register_admin_handlers(application)

    # 11. Admin report review.
    register_admin_reports_handlers(application)

    # 12. Admin Pending purchase queue and manual resolution.
    register_admin_pending_handlers(application)

    # 13. Admin-only audit log browser.
    register_admin_audit_handlers(application)

    # 14. General help command.
    application.add_handler(
        CommandHandler("help", help_command)
    )

    # 15. Global exception logging.
    application.add_error_handler(error_handler)

    logger.info("Starting Telegram bot polling...")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()

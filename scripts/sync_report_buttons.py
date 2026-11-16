import asyncio
import logging

from telegram import Bot

from app.config import settings
from app.database.mongo import connect_db, get_database, close_db
from app.services.channel_service import update_book_channel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await connect_db()
    db = get_database()
    bot = Bot(token=settings.bot_token)
    updated = 0
    failed = 0
    skipped = 0

    try:
        await bot.initialize()
        cursor = db.books.find({
            "status": {"$in": ["Available", "Pending"]},
            "channel_message_id": {"$exists": True, "$ne": None},
        })

        async for book in cursor:
            book_id = str(book.get("_id"))
            try:
                await update_book_channel(
                    bot,
                    book,
                    status=book.get("status"),
                )
                await db.books.update_one(
                    {"_id": book["_id"]},
                    {"$unset": {"channel_sync_error": ""}},
                )
                updated += 1
                logger.info("Updated listing %s", book_id)
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1
                logger.exception("Could not update listing %s", book_id)
                await db.books.update_one(
                    {"_id": book["_id"]},
                    {"$set": {"channel_sync_error": True}},
                )
    finally:
        try:
            await bot.shutdown()
        finally:
            await close_db()

    logger.info(
        "Report-button synchronization complete: updated=%s failed=%s skipped=%s",
        updated,
        failed,
        skipped,
    )


if __name__ == "__main__":
    asyncio.run(main())

"""User registration and Telegram profile synchronization."""
from datetime import datetime, timezone

from app.database.mongo import get_database


async def register_user(user) -> dict:
    """Upsert a Telegram user without replacing marketplace-owned fields."""
    db = get_database()
    now = datetime.now(timezone.utc)
    profile = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "is_bot": bool(user.is_bot),
        "updated_at": now,
    }
    await db.users.update_one(
        {"_id": user.id},
        {
            "$set": profile,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return await db.users.find_one({"_id": user.id}) or {"_id": user.id, **profile}

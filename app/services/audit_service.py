"""Best-effort audit logging for marketplace transaction events."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


async def ensure_audit_indexes(db) -> None:
    """Create indexes used by the admin audit browser."""
    await db.audit_logs.create_index(
        [("created_at", -1)],
        name="audit_created_at_desc",
    )
    await db.audit_logs.create_index(
        [("purchase_request_id", 1), ("created_at", -1)],
        name="audit_request_timeline",
        sparse=True,
    )


async def record_audit_event(
    db,
    *,
    event_type: str,
    actor_id: int | None,
    actor_role: str,
    book_id: ObjectId | None = None,
    request_id: ObjectId | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    """Write an audit event without making the primary business action fail."""
    event = {
        "event_type": str(event_type)[:100],
        "actor_id": actor_id if isinstance(actor_id, int) else None,
        "actor_role": str(actor_role)[:40],
        "book_id": book_id if isinstance(book_id, ObjectId) else None,
        "purchase_request_id": request_id if isinstance(request_id, ObjectId) else None,
        "details": details or {},
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.audit_logs.insert_one(event)
        return True
    except PyMongoError:
        logger.exception(
            "Could not record audit event '%s' for book %s/request %s.",
            event_type,
            book_id,
            request_id,
        )
        return False

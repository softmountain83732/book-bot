"""MongoDB indexes used by the existing marketplace collections."""
from pymongo import ASCENDING, DESCENDING


async def create_indexes(db) -> None:
    """Create indexes aligned with the Bookbot collection/query patterns."""
    # Books
    await db.books.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await db.books.create_index([("seller_id", ASCENDING)])
    await db.books.create_index([("current_buyer_id", ASCENDING)])
    await db.books.create_index([("year", ASCENDING), ("major_slug", ASCENDING), ("status", ASCENDING)])

    # Purchase request history and lifecycle worker scans
    await db.purchase_requests.create_index([("book_id", ASCENDING), ("created_at", DESCENDING)])
    await db.purchase_requests.create_index([("buyer_id", ASCENDING)])
    await db.purchase_requests.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
    await db.purchase_requests.create_index(
        [("book_id", ASCENDING), ("buyer_id", ASCENDING), ("status", ASCENDING)],
        name="book_buyer_request_state",
    )

    # Recovery copy for incomplete /sell conversations across process restarts.
    await db.sell_drafts.create_index([("updated_at", DESCENDING)], name="sell_draft_updated_at")

    # User reports
    await db.reports.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await db.reports.create_index([("book_id", ASCENDING), ("status", ASCENDING)])
    await db.reports.create_index(
        [("reporter_id", ASCENDING), ("book_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "Open"},
        name="one_open_report_per_user_book",
    )

    # The key order and default index name preserve the original unique index.
    await db.favorites.create_index(
        [("user_id", ASCENDING), ("book_id", ASCENDING)],
        unique=True,
    )
    await db.favorites.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])

    # Helpful but non-unique lookup index; safe to add to existing deployments.
    await db.users.create_index([("username", ASCENDING)], sparse=True)

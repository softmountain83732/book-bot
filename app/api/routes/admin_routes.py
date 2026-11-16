# app/api/routes/admin_routes.py
"""Admin system API endpoints: marketplace stats, listing moderation, reports, and purchase audit."""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from telegram import Bot

from app.api.deps import AuthContext, require_admin, get_db
from app.api.schemas.book_schemas import BookDetailResponse, BookListResponse
from app.config import settings
from app.services.audit_service import record_audit_event
from app.services.channel_service import update_book_channel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


class AdminStatsResponse(BaseModel):
    total_users: int
    total_books: int
    available_books: int
    pending_books: int
    sold_books: int
    cancelled_books: int
    delisted_books: int
    pending_requests: int
    open_reports: int


class AdminListingActionRequest(BaseModel):
    action: str  # "hide", "unhide", "cancel"
    reason: Optional[str] = None


class ReportItem(BaseModel):
    id: str
    book_id: str
    book_title: str
    reporter_id: int
    seller_id: int
    reason: str
    reason_label: str
    status: str
    resolved_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReportsListPage(BaseModel):
    items: List[ReportItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class ResolveReportRequest(BaseModel):
    resolution: str  # "Resolved" or "Dismissed"


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_dashboard_stats(
    auth: AuthContext = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieve full live marketplace overview statistics."""
    total_users = await db.users.count_documents({})
    total_books = await db.books.count_documents({"status": {"$ne": "Deleted"}})

    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    cursor = db.books.aggregate(pipeline)
    counts: Dict[str, int] = {}
    async for row in cursor:
        counts[row["_id"]] = row["count"]

    pending_requests = await db.purchase_requests.count_documents({"status": "Pending"})
    open_reports = await db.reports.count_documents({"status": "Open"})

    return AdminStatsResponse(
        total_users=total_users,
        total_books=total_books,
        available_books=counts.get("Available", 0),
        pending_books=counts.get("Pending", 0),
        sold_books=counts.get("Sold", 0),
        cancelled_books=counts.get("Cancelled", 0),
        delisted_books=counts.get("Delisted", 0),
        pending_requests=pending_requests,
        open_reports=open_reports,
    )


@router.get("/books")
async def list_admin_books(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
):
    """List all listings (including delisted/hidden) for moderation."""
    query: Dict[str, Any] = {}
    if status_filter and status_filter != "all":
        query["status"] = status_filter

    if search and search.strip():
        query["title"] = {"$regex": search.strip(), "$options": "i"}

    skip = (page - 1) * page_size
    total = await db.books.count_documents(query)
    cursor = db.books.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    items = []
    async for doc in cursor:
        items.append(BookListResponse.model_validate(doc))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (skip + page_size) < total,
    }


@router.post("/books/{book_id}/action")
async def moderate_book(
    book_id: str,
    body: AdminListingActionRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
):
    """Admin moderation: hide inappropriate listings or cancel problematic items."""
    try:
        oid = ObjectId(book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = await db.books.find_one({"_id": oid})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    now = datetime.now(timezone.utc)
    bot = Bot(token=settings.bot_token)
    action = body.action.lower()

    if action == "hide":
        await db.books.update_one(
            {"_id": oid},
            {"$set": {"admin_hidden": True, "updated_at": now}},
        )
        # Update channel post to reflect cancellation/hidden
        try:
            await update_book_channel(bot, {**book, "admin_hidden": True, "status": "Cancelled"}, status="Cancelled")
        except Exception:
            logger.exception("Failed to update channel post on admin hide")

        await record_audit_event(
            db,
            event_type="admin_hide_book",
            actor_id=auth.user_id,
            actor_role="admin",
            book_id=oid,
            details={"reason": body.reason},
        )
        return {"success": True, "message": "စာအုပ်ကို Admin မှ ဖုံးကွယ် (Hide) လိုက်ပါပြီ။"}

    elif action == "unhide":
        await db.books.update_one(
            {"_id": oid},
            {"$set": {"admin_hidden": False, "updated_at": now}},
        )
        try:
            await update_book_channel(bot, {**book, "admin_hidden": False, "status": book.get("status", "Available")})
        except Exception:
            logger.exception("Failed to update channel post on admin unhide")

        await record_audit_event(
            db,
            event_type="admin_unhide_book",
            actor_id=auth.user_id,
            actor_role="admin",
            book_id=oid,
            details={"reason": body.reason},
        )
        return {"success": True, "message": "စာအုပ်ကို ပြန်လည် ဖော်ပြလိုက်ပါပြီ။"}

    else:
        raise HTTPException(status_code=400, detail="Unsupported moderation action")


@router.get("/reports", response_model=ReportsListPage)
async def list_reports(
    filter_status: str = Query("Open", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
):
    """List open or historical reports."""
    query: Dict[str, Any] = {}
    if filter_status and filter_status != "all":
        query["status"] = filter_status

    skip = (page - 1) * page_size
    total = await db.reports.count_documents(query)
    cursor = db.reports.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    items = []
    async for doc in cursor:
        items.append(
            ReportItem(
                id=str(doc["_id"]),
                book_id=str(doc.get("book_id", "")),
                book_title=doc.get("book_title_snapshot", "Unknown listing"),
                reporter_id=doc.get("reporter_id", 0),
                seller_id=doc.get("seller_id", 0),
                reason=doc.get("reason", "N/A"),
                reason_label=doc.get("reason_label", doc.get("reason", "N/A")),
                status=doc.get("status", "Open"),
                resolved_by=doc.get("resolved_by"),
                created_at=doc.get("created_at", datetime.now(timezone.utc)),
                updated_at=doc.get("updated_at"),
            )
        )

    return ReportsListPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(skip + page_size) < total,
    )


@router.post("/reports/{report_id}/resolve")
async def resolve_report(
    report_id: str,
    body: ResolveReportRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
):
    """Resolve or dismiss an open user report."""
    if body.resolution not in ["Resolved", "Dismissed"]:
        raise HTTPException(status_code=400, detail="Resolution must be Resolved or Dismissed")

    try:
        oid = ObjectId(report_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid report ID")

    now = datetime.now(timezone.utc)
    res = await db.reports.update_one(
        {"_id": oid, "status": "Open"},
        {
            "$set": {
                "status": body.resolution,
                "resolved_by": auth.user_id,
                "resolved_at": now,
                "updated_at": now,
            }
        },
    )

    if res.modified_count != 1:
        raise HTTPException(status_code=400, detail="Report not found or already closed")

    await record_audit_event(
        db,
        event_type="admin_resolve_report",
        actor_id=auth.user_id,
        actor_role="admin",
        details={"report_id": report_id, "resolution": body.resolution},
    )

    return {"success": True, "message": f"Report ကို {body.resolution} အဖြစ် မှတ်သားပြီးပါပြီ။"}

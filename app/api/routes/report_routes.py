# app/api/routes/report_routes.py
"""Public/Buyer book reporting API endpoints."""
from datetime import datetime, timezone
import logging
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.api.deps import AuthContext, get_current_user, get_db
from app.services.audit_service import record_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_REASONS = {
    "fake": "သတင်းအချက်အလက် မမှန်ကန်ခြင်း",
    "spam": "ကြော်ငြာ/Spam ဖြစ်ခြင်း",
    "offensive": "မလျော်ကန်သော အကြောင်းအရာပါဝင်ခြင်း",
    "wrong_major": "မေဂျာ/ပညာသင်နှစ် မှားယွင်းနေခြင်း",
    "other": "အခြား အကြောင်းရင်း",
}


class SubmitReportRequest(BaseModel):
    book_id: str
    reason: str
    notes: Optional[str] = None


class SubmitReportResponse(BaseModel):
    success: bool
    message: str


@router.post("", response_model=SubmitReportResponse)
async def submit_book_report(
    body: SubmitReportRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
):
    """Submit a report for an inappropriate or inaccurate book listing."""
    try:
        oid = ObjectId(body.book_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = await db.books.find_one({"_id": oid})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("seller_id") == auth.user_id:
        raise HTTPException(status_code=400, detail="ကိုယ့်စာအုပ်ကို Report လုပ်၍ မရပါ။")

    reason_key = body.reason.strip().lower()
    reason_label = REPORT_REASONS.get(reason_key, body.reason)

    now = datetime.now(timezone.utc)
    report_doc = {
        "_id": ObjectId(),
        "book_id": oid,
        "reporter_id": auth.user_id,
        "seller_id": book["seller_id"],
        "reason": reason_key,
        "reason_label": reason_label,
        "notes": body.notes,
        "book_title_snapshot": book.get("title", "Untitled"),
        "status": "Open",
        "resolved_by": None,
        "resolved_at": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await db.reports.insert_one(report_doc)
    except DuplicateKeyError:
        return SubmitReportResponse(
            success=True,
            message="ဒီစာအုပ်အတွက် သင့် Report ကို လက်ခံထားပြီး ဖြစ်ပါသည်။",
        )

    await record_audit_event(
        db,
        event_type="user_report_book",
        actor_id=auth.user_id,
        actor_role="buyer",
        book_id=oid,
        details={"reason": reason_label},
    )

    return SubmitReportResponse(
        success=True,
        message="Report ကို လက်ခံရရှိပါသည်။ Admin အဖွဲ့မှ စစ်ဆေးပေးပါမည်။",
    )

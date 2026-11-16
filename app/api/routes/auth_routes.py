# app/api/routes/auth_routes.py
"""Authentication endpoints for Telegram Mini App."""
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.api.auth import (
    TelegramUser,
    create_access_token,
    validate_telegram_init_data,
)
from app.api.deps import AuthContext, get_current_user, get_db
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


class TelegramAuthRequest(BaseModel):
    init_data: str


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: TelegramUser
    is_admin: bool


class UserProfileResponse(BaseModel):
    user_id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    language_code: str | None
    is_admin: bool
    created_at: str | None


@router.post("/telegram", response_model=TelegramAuthResponse)
async def authenticate_telegram(
    body: TelegramAuthRequest,
    db: AsyncDatabase = Depends(get_db),
):
    """Authenticate Telegram Mini App user using raw Telegram.WebApp.initData."""
    try:
        validated = validate_telegram_init_data(body.init_data)
    except ValueError as exc:
        logger.warning("Telegram auth rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    t_user = validated.user
    user_id = t_user.id
    now = datetime.now(timezone.utc)

    # Synchronize / register with existing users collection
    update_data = {
        "username": t_user.username,
        "first_name": t_user.first_name,
        "last_name": t_user.last_name,
        "language_code": t_user.language_code,
        "is_bot": False,
        "updated_at": now,
    }

    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": update_data,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    is_admin = user_id in settings.admin_telegram_ids
    token = create_access_token(user_id=user_id, is_admin=is_admin)

    return TelegramAuthResponse(
        access_token=token,
        token_type="bearer",
        user=t_user,
        is_admin=is_admin,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    auth: AuthContext = Depends(get_current_user),
):
    """Retrieve current authenticated user profile."""
    doc = auth.user_data or {}
    created = doc.get("created_at")
    created_str = created.isoformat() if isinstance(created, datetime) else None

    return UserProfileResponse(
        user_id=auth.user_id,
        first_name=doc.get("first_name"),
        last_name=doc.get("last_name"),
        username=doc.get("username"),
        language_code=doc.get("language_code"),
        is_admin=auth.is_admin,
        created_at=created_str,
    )

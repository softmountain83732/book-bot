
"""FastAPI dependencies for database access, authentication and authorization."""
import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.api.auth import decode_access_token, validate_telegram_init_data
from app.config import settings
from app.database.mongo import get_database

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class AuthContext:
    def __init__(self, user_id: int, is_admin: bool, user_data: Optional[dict] = None):
        self.user_id = user_id
        self.is_admin = is_admin
        self.user_data = user_data or {}


async def get_db() -> AsyncDatabase:
    """Dependency that provides the shared MongoDB database connection."""
    return get_database()


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: AsyncDatabase = Depends(get_db),
) -> Optional[AuthContext]:
    """Return authenticated user when credentials exist, otherwise None."""
    user_id: Optional[int] = None

    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = decode_access_token(credentials.credentials)
            user_id = int(payload["sub"])
        except (ValueError, KeyError, TypeError) as err:
            logger.warning("Invalid JWT credentials provided: %s", err)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
            )

    elif x_telegram_init_data:
        try:
            validated = validate_telegram_init_data(x_telegram_init_data)
            user_id = validated.user.id
        except ValueError as err:
            logger.warning("Failed Telegram initData header validation: %s", err)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Telegram authentication",
            )

    if user_id is None:
        return None

    user_doc = await db.users.find_one({"_id": user_id})
    is_admin_verified = user_id in settings.admin_telegram_ids

    return AuthContext(
        user_id=user_id,
        is_admin=is_admin_verified,
        user_data=user_doc or {},
    )


async def get_current_user(
    auth: Optional[AuthContext] = Depends(get_optional_user),
) -> AuthContext:
    """Require an authenticated user."""
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )
    return auth


async def require_admin(
    auth: AuthContext = Depends(get_current_user),
) -> AuthContext:
    """Enforce administrator permissions."""
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return auth

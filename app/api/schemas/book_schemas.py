# app/api/schemas/book_schemas.py
"""Pydantic response schemas for book-related API endpoints."""
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator


class BookListResponse(BaseModel):
    id: str = Field(alias="_id")
    title: str
    major: str
    major_slug: str
    year: int
    semester: Any
    price: Optional[float] = None
    is_negotiable: bool = False
    condition: str = ""
    condition_details: Optional[str] = None
    seller_id: int
    seller_username: Optional[str] = None
    status: str
    photo_count: int = 0
    has_photos: bool = False
    created_at: datetime
    is_favorite: bool = False

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def compute_photo_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Inspect photo_file_ids list or legacy single photo_file_id
            ids = data.get("photo_file_ids") or []
            if not ids and data.get("photo_file_id"):
                ids = [data["photo_file_id"]]

            computed_count = len(ids)
            if "photo_count" not in data or data["photo_count"] is None:
                data["photo_count"] = computed_count
            elif computed_count > 0 and data["photo_count"] == 0:
                data["photo_count"] = computed_count

            if "has_photos" not in data or data["has_photos"] is None:
                data["has_photos"] = data["photo_count"] > 0
            else:
                data["has_photos"] = bool(data["has_photos"] or data["photo_count"] > 0)

            # Serialize ObjectId to string
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
        return data


class BookDetailResponse(BookListResponse):
    admin_hidden: bool = False
    current_buyer_id: Optional[int] = None
    channel_message_id: Optional[int] = None
    updated_at: Optional[datetime] = None


class BooksListPage(BaseModel):
    items: List[BookListResponse]
    total: int
    page: int
    page_size: int
    has_next: bool

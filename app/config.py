"""Application configuration loaded from environment variables and .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(
        default="",
        validation_alias=AliasChoices("BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
    )
    mongodb_uri: str = Field(
        default="",
        validation_alias=AliasChoices("MONGODB_URI", "MONGO_URI"),
    )
    database_name: str = Field(default="university_marketplace")
    channel_id: str = Field(default="")
    channel_join_url: str = Field(default="")
    bot_username: str = Field(default="")
    admin_ids_raw: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_IDS", "ADMIN_TELEGRAM_IDS"),
    )

    @field_validator("bot_token", "mongodb_uri", "channel_id", "channel_join_url", "bot_username", mode="before")
    @classmethod
    def strip_string_values(cls, value):
        return value.strip() if isinstance(value, str) else value

    @property
    def admin_telegram_ids(self) -> list[int]:
        """Return comma-separated ADMIN_IDS as validated Telegram IDs."""
        result: list[int] = []
        for item in self.admin_ids_raw.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                value = int(item)
            except ValueError:
                continue
            if value not in result:
                result.append(value)
        return result

    @property
    def normalized_bot_username(self) -> str:
        return self.bot_username.strip().removeprefix("@").strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

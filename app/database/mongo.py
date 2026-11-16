"""MongoDB connection management using PyMongo's asynchronous client."""
from __future__ import annotations

import logging
from typing import Any

from pymongo import AsyncMongoClient

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncMongoClient | None = None
_database: Any | None = None


async def connect_db():
    """Connect to MongoDB, verify the connection, and return the database."""
    global _client, _database

    if _client is not None and _database is not None:
        return _database

    if not settings.mongodb_uri:
        raise RuntimeError(
            "MONGODB_URI (or MONGO_URI) is missing from the environment."
        )
    if not settings.database_name:
        raise RuntimeError("DATABASE_NAME is missing from the environment.")

    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        appname="UniversityBookMarketplaceBot",
    )
    try:
        await client.admin.command("ping")
        database = client[settings.database_name]
    except Exception:
        await client.close()
        logger.exception("MongoDB connection or ping failed.")
        raise

    _client = client
    _database = database
    logger.info("Connected to MongoDB database '%s'.", settings.database_name)
    return _database


def get_database():
    """Return the active MongoDB database or raise a clear initialization error."""
    if _database is None:
        raise RuntimeError("MongoDB is not connected. Call connect_db() first.")
    return _database


async def close_db() -> None:
    """Close the MongoDB client and clear global connection state."""
    global _client, _database
    client = _client
    _client = None
    _database = None
    if client is not None:
        await client.close()
        logger.info("MongoDB connection closed.")

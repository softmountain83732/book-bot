# app/api/main.py
"""FastAPI application entry point for HBTU Book Marketplace Mini App API."""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.admin_routes import router as admin_router
from app.api.routes.auth_routes import router as auth_router
from app.api.routes.book_routes import router as book_router
from app.api.routes.favorite_routes import router as favorite_router
from app.api.routes.media_routes import close_media_resources, router as media_router
from app.api.routes.my_books_routes import router as my_books_router
from app.api.routes.purchase_routes import router as purchase_router
from app.api.routes.report_routes import router as report_router
from app.api.routes.sell_routes import router as sell_router
from app.database.indexes import create_indexes
from app.database.mongo import close_db, connect_db, get_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("book_api")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:4173,https://t.me",
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting HBTU Book Marketplace API...")
    await connect_db()
    db = get_database()
    logger.info("MongoDB connected. Ensuring indexes...")
    try:
        await create_indexes(db)
        logger.info("Database indexes ensured.")
    except Exception as exc:
        logger.warning("Index check notice: %s", exc)
    yield
    logger.info("Shutting down...")
    await close_media_resources()
    await close_db()


app = FastAPI(
    title="HBTU Book Marketplace API",
    description="Backend API powering the Telegram Mini App for HBTU students",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global Request Timing & Error Handling Middleware
@app.middleware("http")
async def add_process_time_and_log(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response
    except Exception as exc:
        logger.exception("Unhandled API error on path %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "ဆာဗာတွင် ယာယီအမှားတစ်ခု ဖြစ်ပေါ်နေပါသည်။ ခဏနေမှ ပြန်ကြိုးစားပေးပါ။"},
        )

# Route registrations
app.include_router(auth_router, prefix="/api/v1")
app.include_router(book_router, prefix="/api/v1")
app.include_router(favorite_router, prefix="/api/v1")
app.include_router(purchase_router, prefix="/api/v1")
app.include_router(sell_router, prefix="/api/v1")
app.include_router(my_books_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "hbtu-book-marketplace-api", "version": "1.0.0"}

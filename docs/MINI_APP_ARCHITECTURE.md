# HBTU Book Marketplace — Telegram Mini App Architecture
**Document version:** 1.0.0  
**Status:** Approved / Phase 0 Deliverable  
**Date:** 2026-11-15  

---

## 1. Executive Summary & Objective

The **HBTU Book Marketplace** is an existing production marketplace operating on Telegram for university students in Myanmar (HBTU community). It features:
- A Python Telegram Bot powered by `python-telegram-bot` (v22+ async).
- MongoDB database (`university_marketplace`) with collections: `users`, `books`, `purchase_requests`, `favorites`, `reports`, `audit_logs`, `sell_drafts`.
- Public Telegram broadcast channel for book listings with real-time updates and status changes.
- Multi-step conversational selling workflow (`/sell`).
- Interactive book browsing by academic Year (1 to 6) and Major categories with pagination (`/browse`).
- Atomic purchase request flow with duplicate protection, lifecycle monitoring, and buyer cancellation.
- Seller management portal (`/mybooks`) for delisting, relisting, editing, and channel cleanup.
- Dedicated moderation and auditing dashboard for Administrators (`/admin`).
- Deployment on a Linux VPS managed via PM2 (`ecosystem.config.js` and `run.sh`).

**Objective:**  
Integrate a modern, mobile-first Telegram Mini App (React + TypeScript + Vite) as the primary user interface while strictly preserving the existing Telegram Bot, MongoDB database, business rules, channel synchronization, background tasks, and deployment stability.

---

## 2. Existing System Architecture Audit

### 2.1 Bot Runtime Architecture
- **Framework:** `python-telegram-bot` >= 22.0 (asyncio).
- **Execution Mode:** Long polling via `Application.run_polling()`.
- **Persistence:** Local disk `PicklePersistence(filepath="data/bot_state.pickle")`.
- **Concurrency:** `concurrent_updates=False` (sequential execution of updates per worker).
- **Background Loop:** `asyncio.create_task(pending_lifecycle_loop(application))` in `post_init` hook (`app/main.py`), polling pending purchase requests every 60 seconds (22h warning, 24h seller decision prompt, 48h admin escalation).
- **CRITICAL ARCHITECTURAL FINDING:** Because the bot runs long-polling in a dedicated event loop with persistence and background tasks, the FastAPI backend must run as a **separate process** managed by PM2, sharing the database connection and core business services. Casual combination into a single loop risks starvation and polling crashes.

### 2.2 Database Layer (MongoDB)
- **Driver:** Native `pymongo.AsyncMongoClient` (NOT `motor`), configured in `app/database/mongo.py`.
- **Database Name:** Default `university_marketplace` (configured via `DATABASE_NAME` env var).
- **Lifecycle Management:** Global `_client` and `_database` variables initialized via `connect_db()` and closed via `close_db()`.
- **Collections & Schemas:**
  1. `users`:
     - `_id`: Telegram User ID (`int`)
     - `username`: `str | None`
     - `first_name`: `str | None`
     - `last_name`: `str | None`
     - `language_code`: `str | None`
     - `is_bot`: `bool`
     - `created_at`: `datetime` (UTC)
     - `updated_at`: `datetime` (UTC)
  2. `books`:
     - `_id`: `ObjectId`
     - `title`: `str`
     - `major`: `str` (Display label: "CEIT", "EP", "EC", "Architecture", "MC", "Mechanical", "Civil")
     - `major_slug`: `str` ("ceit", "ep", "ec", "arch", "mc", "mech", "civil")
     - `year`: `int` (1 to 6)
     - `semester`: `int | str` (1, 2, 3, 4, "1 & 2", "3 & 4")
     - `price`: `int | float | None`
     - `is_negotiable`: `bool`
     - `condition`: `str` (e.g. "အသစ်နီးပါး", "အတော်အသင့်ကောင်း", "အသုံးပြုထားသည်")
     - `photo_file_ids`: `list[str]` (1 to 4 Telegram file IDs)
     - `photo_file_id`: `str | None` (Legacy single-photo reference)
     - `seller_id`: `int` (Telegram user ID)
     - `seller_username`: `str | None`
     - `status`: `str` ("Available", "Pending", "Sold", "Cancelled", "Delisted", "Deleted")
     - `admin_hidden`: `bool`
     - `current_buyer_id`: `int | None`
     - `channel_id`: `str | None`
     - `channel_message_id`: `int | None`
     - `channel_post_type`: `str` ("photo" for single, "text" for album+caption)
     - `channel_photo_message_ids`: `list[int]`
     - `channel_sync_error`: `bool` (optional flag)
     - `created_at`: `datetime`
     - `updated_at`: `datetime`
  3. `purchase_requests`:
     - `_id`: `ObjectId`
     - `book_id`: `ObjectId`
     - `seller_id`: `int`
     - `buyer_id`: `int`
     - `status`: `str` ("Pending", "CancelledByBuyer", "Sold", "BuyerUnresponsive", "ReleasedBySeller", "CancelledBySeller", "NotificationFailed", "ReconciledStale", "AdminCancelled")
     - `created_at`: `datetime`
     - `updated_at`: `datetime`
     - `buyer_message_id`: `int | None`
     - `buyer_message_chat_id`: `int | None`
     - `seller_message_id`: `int | None`
     - `seller_message_chat_id`: `int | None`
     - `cancelled_by`: `int | None`
     - `cancelled_at`: `datetime | None`
     - Lifecycle fields: `seller_warning_sent_at`, `seller_decision_requested_at`, `seller_decision`, `seller_decision_at`, `admin_escalated_at`
  4. `favorites`:
     - `user_id`: `int`
     - `book_id`: `ObjectId`
     - `created_at`: `datetime`
  5. `reports`:
     - `_id`: `ObjectId`
     - `book_id`: `ObjectId`
     - `reporter_id`: `int`
     - `seller_id`: `int`
     - `reason`: `str`
     - `reason_label`: `str`
     - `book_title_snapshot`: `str`
     - `status`: `str` ("Open", "Resolved", "Dismissed")
     - `resolved_by`: `int | None`
     - `resolved_at`: `datetime | None`
     - `created_at`: `datetime`
     - `updated_at`: `datetime`
  6. `audit_logs`:
     - `_id`: `ObjectId`
     - `event_type`: `str`
     - `actor_id`: `int | None`
     - `actor_role`: `str` ("buyer", "seller", "system", "admin")
     - `book_id`: `ObjectId | None`
     - `purchase_request_id`: `ObjectId | None`
     - `details`: `dict`
     - `created_at`: `datetime`
  7. `sell_drafts`:
     - `_id`: `int` (Telegram user ID)
     - `chat_id`: `int`
     - `state`: `int` (0 to 6)
     - `draft`: `dict`
     - `updated_at`: `datetime`

### 2.3 Critical Business Logic & Rules
1. **Academic Semester Mapping:**
   - **Year 1, 3, 4, 5, 6:** Semester 1, Semester 2, Both (1 & 2).
   - **Year 2:** Semester 3, Semester 4, Both (3 & 4).
   - *Legacy Year 2 records:* May exist as 1, 2, "1 & 2". `format_semester()` in `channel_service.py` safely normalizes legacy Year 2 displays.
2. **Channel Publishing Logic:**
   - Single photo -> `bot.send_photo()` with caption & inline keyboard -> `channel_post_type = "photo"`.
   - 2-4 photos -> `bot.send_media_group()` followed by `bot.send_message()` with caption & buttons -> `channel_post_type = "text"`.
   - On status changes, `update_book_channel()` edits the photo caption or the text message accordingly.
3. **Atomic Purchase Flow:**
   - `db.books.update_one({"_id": book_id, "status": "Available", "admin_hidden": {"$ne": True}}, {"$set": {"status": "Pending", "current_buyer_id": buyer_id}})` ensures race conditions between simultaneous buyers are strictly prevented.
   - Buyers cannot buy their own listings (`seller_id != buyer_id`).
   - Duplicate active pending requests are rejected by compound query and unique index.
4. **Buyer Cancellation Flow:**
   - Buyer can cancel only their own pending request.
   - Atomic verification ensures book is still Pending with `current_buyer_id == buyer_id`.
   - Re-checks whether other pending requests exist before restoring status to `Available`.
   - Updates channel post and notifies seller via Bot.

---

## 3. Mini App Proposed Architecture

```
+---------------------------------------------------------------------------------+
|                                 VPS Deployment                                  |
|                                                                                 |
|  +--------------------+         +--------------------+                          |
|  |   Nginx (Port 443) |         |      MongoDB       |                          |
|  |  SSL/HTTPS Domain  |         | (Existing cluster) |                          |
|  +----+----------+----+         +----+----------+----+                          |
|       |          |                   ^          ^                               |
|       | Static   | Reverse Proxy     |          |                               |
|       v          v                   |          |                               |
|  +-----------+  +--------------------+--+     +-+----------------------------+  |
|  |  Frontend |  |  FastAPI Backend API  |     |  Existing Telegram Bot       |  |
|  |  React/TS |  |  (Uvicorn - Port 8000)|     |  (PTB Long Polling + Loops)  |  |
|  |  Vite SPA |  |  PM2: "book-api"      |     |  PM2: "my-python-app"        |  |
|  +-----------+  +------------+----------+     +--------------+---------------+  |
|                              |                               |                  |
|                              +------------ Telegram Bot API -+                  |
|                                            (Shared Token)                       |
+---------------------------------------------------------------------------------+
```

### 3.1 Separation of Concerns & Process Architecture
1. **Existing Bot Process (`my-python-app` via PM2):**
   - Retains long polling, ConversationHandlers, keyboard callbacks, and background lifecycle loop (`pending_lifecycle_loop`).
   - Handles inbound bot chats and background escalations.
2. **FastAPI Backend Process (`book-api` via PM2):**
   - High-performance asynchronous REST API running under Uvicorn.
   - Reuses `app/database/mongo.py` connection management.
   - Uses an independent `telegram.Bot(token=settings.bot_token)` instance for triggering seller/buyer notifications and channel post modifications.
   - Exposes clean, versioned `/api/v1/` endpoints for the React Mini App.

### 3.2 Authentication & Security Architecture
- **Raw initData Validation:**  
  The frontend retrieves `window.Telegram.WebApp.initData` and transmits it in the `Authorization: tma <initData>` header or via `POST /api/v1/auth/telegram`.
- **HMAC-SHA-256 Validation:**  
  1. Parse query string into key-value pairs, extracting `hash`.
  2. Alphabetically sort pairs (`k=v`), join with `\n` to form `data_check_string`.
  3. Derive secret key via HMAC-SHA-256 with key `"WebAppData"` and message `BOT_TOKEN`.
  4. Compute HMAC-SHA-256 of `data_check_string` with secret key.
  5. Compare computed hash with received hash in constant time (`hmac.compare_digest`).
  6. Check `auth_date`: reject if older than 86,400 seconds (24h) to prevent replay attacks.
  7. Parse JSON `user` field, verify presence of `id`, and register/sync user via existing logic.
- **Session Tokens:**  
  After validation, issue a signed JWT session token (or direct stateless verified TMA token) containing `user_id` and role (`user` vs `admin`).
- **Authorization Dependency:**  
  `get_current_user` FastAPI dependency extracts and validates the Telegram user, ensuring zero trust in client-supplied identifiers.

### 3.3 Telegram Photo Delivery & Staging Architecture
- Telegram `photo_file_ids` cannot be directly loaded as HTTPS URLs by browsers without revealing the `BOT_TOKEN`.
- **Image Proxy Endpoint:**  
  `GET /api/v1/books/{book_id}/photos/{photo_index}`:
  1. Validates that `book_id` exists and is not admin-hidden.
  2. Retrieves `photo_file_ids[photo_index]`.
  3. Resolves Telegram file path via `bot.get_file(file_id)`.
  4. Streams the image bytes with `Cache-Control: public, max-age=86400`.
- **Sell Photo Upload & Staging:**  
  1. When seller selects up to 4 images in the Mini App, images are uploaded as `multipart/form-data` to `POST /api/v1/sell/upload-staging`.
  2. Files are validated (format: JPG/PNG/WebP, max size 10MB per image, max 4 files).
  3. Files are stored in a secure local staging folder (`data/staging/{user_id}/`).
  4. On listing confirmation (`POST /api/v1/sell/publish`), the backend uses the Bot API to publish directly to the channel via `send_photo` or `send_media_group`, capturing the generated `photo_file_ids`.
  5. The MongoDB document is created and staged local files are immediately cleaned up.

---

## 4. Reusable Services & Component Refactoring Plan

| Component / Service | Current Location | Reusability | Action Required |
|---|---|---|---|
| MongoDB Connection | `app/database/mongo.py` | 100% Reusable | Reused directly by FastAPI application lifecycle |
| Database Indexes | `app/database/indexes.py` | 100% Reusable | Keep existing indexes intact; add supplemental indexes if needed |
| User Registration | `app/services/user_service.py` | 95% Reusable | Add overloaded adapter to accept dict / Pydantic schema in addition to `telegram.User` |
| Audit Logging | `app/services/audit_service.py` | 100% Reusable | Call `record_audit_event()` from API endpoints |
| Channel Publishing | `app/services/channel_service.py` | 100% Reusable | `format_semester()`, `build_book_caption()`, and `update_book_channel()` can be invoked using the API's Bot instance |
| Purchase Atomic Operations | `app/handlers/purchase.py` | Needs Extraction | Extract atomic book claim & request creation into `app/services/purchase_service.py` so both Bot and API share the exact same logic |
| Channel Message Deletion | `app/handlers/my_books.py` | Needs Extraction | Extract `_delete_channel_listing_posts()` into `channel_service.py` |
| Year 2 Semester Rules | `app/handlers/sell.py`, `channel_service.py` | 100% Reusable | Centralize `_semester_values()` into a shared academic helper module |

---

## 5. Security & Risk Analysis

1. **Secret Exposure:**  
   - Frontend is a static client; `BOT_TOKEN` and `MONGODB_URI` must NEVER be placed in frontend `.env` or Vite build variables.
2. **Replay & Tampering Attacks:**  
   - Handled via HMAC-SHA-256 validation of `initData` and checking `auth_date` expiry.
3. **Privilege Escalation:**  
   - Admin access is granted STRICTLY by verifying `user_id in settings.admin_telegram_ids`. Client-supplied roles are completely ignored.
4. **Channel Sync Failures:**  
   - If Telegram API fails during channel updates, flag `channel_sync_error: True` in MongoDB without rolling back database records, alerting admins for automated retry.

---

## 6. Directory Structure Blueprint

```
minapp/
├── bookbot/
│   ├── app/
│   │   ├── api/                   # NEW: FastAPI API Module
│   │   │   ├── __init__.py
│   │   │   ├── main.py            # FastAPI entry point & lifespan
│   │   │   ├── deps.py            # Auth & DB dependencies
│   │   │   ├── routes/
│   │   │   │   ├── auth.py        # /api/v1/auth
│   │   │   │   ├── books.py       # /api/v1/books (Browse & Search)
│   │   │   │   ├── purchases.py   # /api/v1/purchases (Buy & Cancel)
│   │   │   │   ├── favorites.py   # /api/v1/favorites
│   │   │   │   ├── sell.py        # /api/v1/sell
│   │   │   │   ├── my_books.py    # /api/v1/my-books
│   │   │   │   ├── admin.py       # /api/v1/admin
│   │   │   │   └── media.py       # /api/v1/media (Photo proxy)
│   │   │   └── schemas/           # Pydantic models for req/res
│   │   ├── database/              # Reused
│   │   ├── handlers/              # Reused bot handlers
│   │   ├── keyboards/             # Reused bot keyboards
│   │   └── services/              # Shared business logic
│   ├── docs/                      # Documentation
│   ├── frontend/                  # NEW: React + TypeScript + Vite Mini App
│   │   ├── src/
│   │   │   ├── api/               # Centralized Axios / fetch client
│   │   │   ├── components/        # Reusable UI widgets
│   │   │   ├── layouts/           # App shell & BottomNav
│   │   │   ├── pages/             # Route pages
│   │   │   ├── hooks/             # Telegram WebApp & query hooks
│   │   │   └── types/             # TypeScript definitions
│   │   ├── index.html
│   │   ├── package.json
│   │   └── vite.config.ts
│   ├── ecosystem.config.js        # Multi-process PM2 config
│   └── run.sh
```

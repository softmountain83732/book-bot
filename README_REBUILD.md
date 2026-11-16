# University Book Marketplace Bot — Reconstructed Source

This package combines source files recovered from the prior conversation with newly reconstructed missing modules. It is intended to restore the project structure and feature paths through Phase 14. The reconstructed files are new compatible implementations, not byte-for-byte copies of the lost originals.

## Included layers

- `app/handlers/`: Telegram commands, conversations and callback handlers
- `app/services/`: application/business services (Mongo-backed user registration, channel membership, deep-link routing, audit and pending lifecycle)
- `app/database/`: async MongoDB connection and indexes
- `app/keyboards/`: inline-keyboard builders
- `scripts/`: maintenance scripts

## Configuration

Copy `.env.example` to `.env` and set:

- `BOT_TOKEN`
- `MONGODB_URI` (or `MONGO_URI`)
- `DATABASE_NAME`
- `CHANNEL_ID`
- `CHANNEL_JOIN_URL`
- `BOT_USERNAME`
- `ADMIN_IDS` (comma-separated numeric Telegram IDs)

The bot must be an administrator in the listing channel so it can publish/edit posts and check membership.

## Dependencies

Python 3.11+ is recommended. Install the packages from `requirements.txt` in your existing virtual environment.

## Data compatibility

The MongoDB database name defaults to `university_marketplace`. Existing data collections are expected to be:

- `users`
- `books`
- `purchase_requests`
- `favorites`
- `reports`
- `audit_logs`

The `books` documents use `seller_id`, `title`, `major`, `year`, `semester`, `price`, `is_negotiable`, `condition`, `photo_file_id`, `status`, `channel_id`, and `channel_message_id` fields. Purchase lifecycle uses `purchase_requests.created_at`, `status`, `seller_id`, and `buyer_id`.

**Important:** before using this reconstruction against an existing production database, back up MongoDB. The index setup includes a unique partial index that allows only one Open report per user/listing. If legacy duplicate Open reports exist, index creation will need cleanup first.

## Verification status

All included `.py` files pass Python syntax compilation. This environment did not have the project's Python dependencies installed and was not connected to the user's Telegram bot or MongoDB, so end-to-end runtime behavior has not been verified. Run a staging test before replacing a live bot.

# Bookbot source reconstruction status

## Source recovered from prior saved files

- `app/main.py`
- `app/handlers/admin_audit.py`
- `app/handlers/admin_pending.py`
- `app/handlers/admin_reports.py` (recovered full handler text)
- `app/handlers/favorites.py` (recovered full handler text)
- `app/handlers/purchase.py`
- `app/handlers/reports.py`
- `app/handlers/seller_control.py`
- `app/keyboards/pending_lifecycle.py`
- `app/services/audit_service.py`
- `app/services/channel_service.py`
- `app/services/pending_lifecycle_service.py`
- `scripts/sync_report_buttons.py`

## Missing modules reconstructed in this package

- `app/config.py`
- `app/database/mongo.py`
- `app/database/indexes.py`
- `app/handlers/subscription.py`
- `app/handlers/start.py`
- `app/handlers/sell.py`
- `app/handlers/my_books.py`
- `app/handlers/browse.py`
- `app/handlers/admin.py`
- `app/keyboards/main_menu.py`
- `app/keyboards/subscription.py`
- `app/keyboards/book_actions.py`
- `app/keyboards/report.py`
- `app/keyboards/admin.py`
- `app/keyboards/favorites.py`
- `app/services/subscription_service.py`
- `app/services/user_service.py`
- `app/services/deep_link_service.py`

These missing modules were newly written to match import names, callback formats, MongoDB collection names, and fields used by the recovered Phase 12–14 handlers. They are not the original deleted file contents.

## Limitations

- `.env` and all secrets are intentionally excluded.
- Python syntax compilation passes, but no live Telegram/MongoDB end-to-end test was possible here.
- Back up the production database before deployment. Existing duplicate Open reports could prevent creation of the partial unique report index.

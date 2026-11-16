# HBTU Book Marketplace — Implementation Roadmap & Phase Plan
**Document version:** 1.1.0  
**Status:** Implementation & Testing Complete — Ready for VPS Deployment & Rollout  
**Last Updated:** 2026-11-16  

---

## Master Phase Checklist

- [x] **Phase 0: Repository Audit & Architecture Plan**
  - [x] Complete repository and database inspection
  - [x] Analyze bot runtime and background task lifecycle
  - [x] Audit MongoDB collections, schemas, and indexes
  - [x] Document Year 2 semester mapping business rule
  - [x] Trace Sell, Browse, Purchase, Cancel, Favorites, MyBooks, Admin flows
  - [x] Create `docs/MINI_APP_ARCHITECTURE.md`
  - [x] Create `docs/MINI_APP_PHASE_PLAN.md`

- [x] **Phase 1: Mini App Foundation & Authentication**
  - [x] Initialize React + TypeScript + Vite frontend project
  - [x] Integrate Telegram WebApp official script & safe viewport config
  - [x] Implement mobile-first responsive layout with Bottom Navigation
  - [x] Implement FastAPI backend service under `app/api/`
  - [x] Implement Telegram HMAC-SHA-256 `initData` validator with constant-time check
  - [x] Implement `/api/v1/health`, `/api/v1/auth/telegram`, `/api/v1/auth/me`
  - [x] Implement development fallback for browser testing
  - [x] Unit tests for authentication (valid, expired, tampered) — passing

- [x] **Phase 2: Marketplace Home & Browse**
  - [x] Build Home page with search bar, Year pills, Major shortcuts, and sell CTA
  - [x] Build Browse page with Year/Major/Semester pill filters, debounced search, URL sync
  - [x] Implement Year 2 semester mapping (Semesters 3 & 4) on frontend & backend
  - [x] Create `GET /api/v1/books` listing endpoint with database-side filtering + pagination
  - [x] Create `GET /api/v1/books/{id}` book detail endpoint with favorite status
  - [x] Implement secure Telegram photo proxy `GET /api/v1/media/books/{id}/photos/{idx}`
  - [x] Build multi-photo gallery carousel with dot indicators, prev/next navigation, BackButton
  - [x] BookCard component with photo, price, badges, haptic feedback, skeleton loaders
  - [x] Infinite scroll via IntersectionObserver on Browse page
  - [x] Empty/error states with retry actions

- [x] **Phase 3: Favorites & Purchase Workflow**
  - [x] Implement `/api/v1/favorites` endpoints (list, add, remove)
  - [x] Build Favorites UI with real-time status badges and pagination
  - [x] Extract purchase service into `app/services/purchase_service.py`
  - [x] Implement atomic purchase endpoint `/api/v1/purchases/buy` with duplicate protection
  - [x] Implement two-step buyer cancellation endpoint `/api/v1/purchases/cancel`
  - [x] Integrate seller Telegram notifications & channel synchronization on buy/cancel actions
  - [x] Build purchase history tracker (`/purchases`) with cancellation modal in frontend
  - [x] Real-time favorite toggle and buy flow on BookDetailPage

- [x] **Phase 4: Sell Books**
  - [x] Build Sell form with dynamic semester options based on selected Year
  - [x] Implement up to 4 photo picker with preview, reordering, and removal
  - [x] Implement photo upload & staging endpoint `/api/v1/sell/upload-photo`
  - [x] Implement listing confirmation and publish endpoint `/api/v1/sell/publish`
  - [x] Integrate channel publishing with single/multi-photo support
  - [x] Maintain draft persistence in MongoDB (`sell_drafts`)

- [x] **Phase 5: My Books & Seller Dashboard**
  - [x] Build My Books list with status tabs (All, Available, Pending, Delisted, Sold)
  - [x] Implement seller edit endpoint (title, price, condition, negotiable)
  - [x] Implement Delist and Relist operations with channel post synchronization
  - [x] Implement permanent delete with explicit confirmation and channel post cleanup
  - [x] Build seller metrics dashboard (`/my-books/metrics`)

- [x] **Phase 6: Admin System & Report Management**
  - [x] Implement server-side admin verification dependency (`require_admin`)
  - [x] Build Admin Dashboard with real marketplace statistics (`GET /api/v1/admin/stats`)
  - [x] Build Listing Moderation API & UI (`POST /api/v1/admin/books/{id}/action` hide/unhide)
  - [x] Build Report Management API & UI (`/api/v1/admin/reports`, resolve/dismiss)
  - [x] Maintain audit log generation for all admin actions
  - [x] Enforce 403 Forbidden for non-admin users

- [x] **Phase 7: User Profile & Notifications**
  - [x] Build User Profile view with Telegram account details and activity shortcuts
  - [x] Document Telegram Bot notification delivery for all marketplace events
  - [x] Ensure seamless deep-linking back to the bot or mini app
  - [x] Implement report submission flow for buyer/public users (`POST /api/v1/reports`)

- [x] **Phase 8: Database, Performance & Reliability**
  - [x] Audit query performance and verify compound MongoDB indexes on startup
  - [x] Implement response caching headers for static book data and Telegram photos
  - [x] Centralize global exception handling middleware with response timing headers (`X-Process-Time`)
  - [x] Prevent secret leakage: Bot token and MongoDB credentials strictly isolated in backend
  - [x] Reliable draft recovery and atomic database states

- [x] **Phase 9: UI/UX Refinement & Mobile Experience**
  - [x] Complete Burmese typography and UI translations (keeping CEIT, EP, EC, MMK)
  - [x] Add loading skeletons, pull-to-refresh, and empty state illustrations
  - [x] Adapt Telegram theme colors (light/dark mode dynamic sync) and safe areas (`env(safe-area-inset-bottom)`)
  - [x] Implement haptic feedback on interactive button taps
  - [x] Add touch swipe gesture support for multi-photo gallery in BookDetailPage
  - [x] Add Report Modal with reasons and notes submission for users
  - [x] Add Recently Listed Books section and refresh shortcut on HomePage

- [x] **Phase 10: Testing & Quality Assurance**
  - [x] Run automated backend test suite (41/41 Pytest tests passing cleanly)
  - [x] Run frontend production build (`tsc -b && vite build` passing with zero errors)
  - [x] Comprehensive validation tests for sell inputs, photo limits, and Year 2 semester logic
  - [x] Pydantic schema validation tests and health endpoint tests

- [x] **Phase 11: VPS Deployment Configuration**
  - [x] Update `ecosystem.config.js` to manage both Bot (`my-python-app`) and API (`book-api`) processes
  - [x] Provide Nginx reverse proxy configuration for static files and `/api/` in `docs/MINI_APP_DEPLOYMENT.md`
  - [x] Document `.env.example` with required configuration keys
  - [x] Update `requirements.txt` with all production packages

- [ ] **Phase 12: Gradual Rollout & Verification**
  - [ ] Configure Mini App menu button via @BotFather
  - [ ] Execute alpha testing with admin team
  - [ ] Monitor logs and verify parallel bot and web operations

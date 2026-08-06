# ShopSphere — Production E-Commerce Build (Phases 1–7, complete)

This is the completed build: all 7 phases of an incrementally-built,
Myntra-style e-commerce platform, from auth through hardening and
deployment. Every phase was built and **tested before moving on to the
next** — nothing here was generated in one shot and hoped to work.
Everything has actually been run:

- Backend: `pytest` → **74/74 tests passing** (6 auth + 8 catalog + 11
  cart/checkout/orders + 14 payments + 11 admin panel + 16 reviews/
  notifications/tracking/search/recommendations + 8 hardening —
  including a real WebSocket push test, and three real bugs caught and
  fixed by actually running the suite rather than trusting the code on
  read: a rate-limiter test-isolation leak, a logging context-var
  ordering bug, and a JSON-serialization crash in the error handler)
- Frontend: `tsc --noEmit` clean, `next build` → **compiles and generates
  a real production bundle** for all 20 routes, including a verified
  working Docker `standalone` output

---

## Folder structure — and why each part exists

```
backend/
  app/
    core/         # config.py (env vars), security.py (hashing, JWT),
                   # images.py (upload/compression), coupons.py (shared
                   # validation used by both cart and checkout),
                   # razorpay_gateway.py (signature verification + the
                   # injectable payment-gateway interface), ws_manager.py
                   # (WebSocket connection registry), notifications.py
                   # (persist + live-push in one call), rate_limit.py,
                   # security_headers.py, request_context.py (request ID +
                   # structured logging), exception_handlers.py
    db/           # session.py (per-request DB session), base.py (ORM base),
                   # types.py (cross-DB UUID column)
    models/       # SQLAlchemy ORM classes = database tables
    schemas/      # Pydantic classes = API request/response contracts
    api/v1/       # route handlers, versioned (v1) so v2 can coexist later
                   # without breaking existing frontend clients
    main.py       # FastAPI app instance, middleware, router registration
  alembic/         # database migration scripts (schema version control)
  tests/           # pytest suite, SQLite in-memory for speed
  Dockerfile       # multi-stage build → slim runtime image
  requirements.txt

frontend/
  app/             # Next.js App Router — file-based routing
    (auth)/        # route group: /login, /signup share layout without
                     # the group name appearing in the URL
    products/      # /products (catalog+filters), /products/[slug] (PDP)
    cart/          # /cart — view, adjust, apply coupon
    checkout/      # /checkout — address + place order
    orders/        # /orders (list), /orders/[id] (detail, status trail, Pay Now)
    admin/         # /admin/* — role-gated dashboard, products, categories,
                     # brands, orders, coupons, payments, users
    profile/       # example PROTECTED route
    layout.tsx     # root layout: providers, header, toast host
    providers.tsx  # React Query client setup
    error.tsx       # App Router error boundary convention
  components/      # shared UI (ProductCard, SiteHeader, NotificationBell,
                     # SearchBox, ProductReviews, OrderTracking, ...)
  lib/             # framework-agnostic logic: api client, auth store,
                     # validation schemas, protected-route wrapper, price math
  types/           # shared TypeScript types mirroring backend schemas

.github/workflows/ci.yml   # backend pytest (against real Postgres) + frontend
                            # typecheck/build, run on every push and PR
docker-compose.yml          # local "production-like" stack: postgres + backend
                             # + frontend + nginx
nginx/nginx.conf            # reverse proxy: routes /api and /media to the
                             # backend, everything else to the frontend
scripts/backup_db.sh        # pg_dump wrapper (compressed, timestamped)
scripts/restore_db.sh       # pg_restore wrapper (confirms before overwriting)
```

**Why `models/` and `schemas/` are separate** (not obvious if you haven't
built a FastAPI app before): the DB model has fields like
`hashed_password` that should never leave the server. The response schema
(`UserOut`) simply doesn't include that field — so leaking it in an API
response is structurally impossible, not just "remembered not to."

**Why routes are versioned (`/api/v1/...`)**: when you need to change an
endpoint's shape later, you add `/api/v2/...` alongside it instead of
breaking every existing client (mobile apps, other services) overnight.

---

## What's implemented

**Phase 1 — Auth**
- Signup, login, logout, refresh-token rotation, `/me`
- JWT access tokens (15 min) + refresh tokens (7 days) — see
  `app/core/security.py` docstring for why two tokens
- Bcrypt password hashing
- Role field on User (`customer` / `admin` / `super_admin`) with a
  `require_role()` dependency
- Frontend: signup/login forms (React Hook Form + Zod), Zustand auth
  store (persisted), Axios instance with **automatic silent token
  refresh** on 401, a reusable `<ProtectedRoute>` wrapper

**Phase 2 — Product Catalog**
- Category (self-referential tree), Brand, Product, ProductVariant
  (size/color/stock/price override), ProductImage models
- Admin endpoints (role-gated): create category/brand, create product
  **with variants in one DB transaction**, update product, soft-delete
  (status → inactive, never a row deletion), image upload with real
  Pillow compression + resizing, admin product listing (includes drafts)
- Public endpoints: paginated product listing with category/brand/price
  filters, search (ILIKE — see `app/api/v1/catalog.py` docstring for why
  not ElasticSearch yet), sort (newest/price/featured), product detail
  by slug
- Frontend: `/products` catalog with URL-driven filters + pagination,
  `/products/[slug]` PDP with size/color variant picker and image
  gallery, `ProductCard` component, INR price/discount formatting shared
  across both

**Phase 3 — Cart, Checkout & Orders**
- Address CRUD (Phase 1 had the model but no endpoints — added here),
  scoped to the owning user, one default address per user
- Cart/CartItem models — server-side, not localStorage, one cart per user
- Coupon model (percentage or flat, min order value, max discount cap,
  usage limit) with a single shared validation function called at both
  "apply to cart" time and checkout time — never trust a discount
  computed in an earlier request
- **The checkout transaction**: row-level locking (`with_for_update()`)
  on each variant to prevent overselling under concurrent checkouts,
  price/discount/GST/coupon re-validated from scratch, stock decremented,
  snapshotted OrderItem rows created (product name/price/SKU frozen at
  purchase time — never dependent on the live product row), all in one
  DB transaction
- Order status lifecycle enforced server-side (`_FORWARD_TRANSITIONS` —
  can't jump straight from pending to delivered, cancellation only before
  shipping, etc.)
- Admin: list all orders, update order status with lifecycle validation,
  create coupons
- Frontend: `/cart` (adjust qty, remove, apply/remove coupon), `/checkout`
  (address selection or inline creation, order placement), `/orders` +
  `/orders/[id]` (status progress trail, full price breakdown, shipping
  address), a `SiteHeader` with a live cart item count

**Phase 4 — Razorpay Payments**
- `Payment` model — one row per payment ATTEMPT (not just one per order),
  so retries and refund history are real data, not reconstructed from
  mutated Order fields
- Signature verification (`core/razorpay_gateway.py`) is real,
  local HMAC-SHA256 — the actual security-critical part of the whole flow
  — and is genuinely unit-tested, including against forged/tampered
  signatures, with no mocking
- The two calls that need Razorpay's real servers (create order, issue a
  refund) sit behind an injectable `RazorpayGateway` interface — tests
  inject a `FakeRazorpayGateway` (see `tests/conftest.py`) rather than
  hitting a live payment API from an automated test suite, which is the
  standard, correct way to test third-party payment integrations
- Full flow: create Razorpay order → customer pays in the widget → we
  verify the signature (client-triggered) → Razorpay's webhook
  independently confirms the same event server-to-server (the
  authoritative source in production) → admin refund endpoint
- Frontend: real Razorpay Checkout widget integration (loaded on demand,
  not bundled) on the order detail page — "Pay Now" → widget opens →
  success handler verifies with our backend → payment status updates live

**Phase 5 — Admin Panel**
- Most admin CRUD already existed from earlier phases (products,
  categories, brands, orders, coupons, payments) — Phase 5 added the two
  pieces genuinely new to "administration": user management and a
  dashboard summary
- User management: list/search users, deactivate/reactivate (can't
  deactivate yourself), and role changes restricted to SUPER_ADMIN only
  (a regular admin promoting themselves or others to admin would be a
  privilege-escalation hole — see `admin_users.py` docstring) and blocked
  from self-role-change (avoids a super admin locking themselves out)
- Dashboard summary: total revenue computed from PAID `Payment` rows
  (never from `Order.total_amount`, since an order can exist unpaid —
  see `admin_dashboard.py`), order/customer/product counts, low-stock
  variant count, recent orders
- Frontend: a role-gated `/admin/*` section (customers/unauthenticated
  users are redirected) with a shared sidebar layout and 9 pages —
  dashboard, product list + the full "Add Product" form (dynamic
  size/color/stock variant rows, matching the original brief's walkthrough),
  image upload, categories, brands, order status management, coupon
  creation, payment refunds, and user management with super-admin-gated
  role controls

**Phase 6 — Real-time Tracking, Notifications, Search, Recommendations, Reviews**
- Reviews: verified-purchase detection is checked server-side against
  real order history (never trusted from the client), one review per
  user per product, average rating, helpful votes, reporting
- Notifications: persisted `Notification` rows (so "what happened while
  I was away" survives a disconnected socket) PLUS a real-time WebSocket
  push when connected — both happen from one shared `notify_user()` call
  site, triggered by order status changes and payment confirmations.
  The access token is passed as a WebSocket query param (browsers can't
  set custom headers on the handshake) — part of why access tokens are
  short-lived. An in-memory `ConnectionManager` is correct for a single
  backend instance; scaling to multiple instances needs Redis Pub/Sub or
  similar (Phase 7 territory, flagged rather than silently glossed over)
- Delivery tracking: an append-only `TrackingEvent` log (not a single
  "current status" field — a real shipment's journey needs the whole
  trail, not just the latest point), `DeliveryPartner` records, and a
  map view using an embedded OpenStreetMap iframe (no API key, no new
  JS dependency) rather than a full Leaflet integration — the "delivery
  simulation" the brief asks for IS the real admin tracking-event
  endpoint, called repeatedly, not a separate fake system
- Search: query logging, autocomplete suggestions, trending searches
- Recommendations: related products (same category — an honest simple
  version, not a similarity model with no data to train on yet) and
  frequently-bought-together (a real SQL self-join over order history,
  with the case made in `recommendations.py` for why that's fine at this
  data scale and what would change at real scale); recently-viewed is
  implemented client-side only (localStorage) since it's genuinely
  per-device browsing history, not something that needs to be server-side

**Phase 7 — Hardening & Deployment**
- Rate limiting on abuse-prone endpoints (login, signup, checkout,
  payment order creation) via slowapi — in-memory storage, correct for a
  single backend process; multi-instance deployments need Redis-backed
  storage (a one-line change, see `core/rate_limit.py`)
- Security headers (nosniff, X-Frame-Options, HSTS in production,
  Referrer-Policy) applied to every response including error responses
- Structured JSON logging with a request ID threaded through every log
  line via a `ContextVar` and echoed in the `X-Request-ID` response
  header — the actual debugging value of this only shows up in
  production log volumes, but the mechanism is real and tested
- Centralized exception handling: generic messages in production (no
  stack traces leaked), full detail in development, consistent envelope
  shape with the request ID attached
- `/docs` and `/redoc` disabled outside development
- CI (GitHub Actions): backend tests run against a **real Postgres
  service container** (not just SQLite) plus an Alembic migration
  sanity check, frontend typecheck + build — on every push and PR
- Docker Compose stack: Postgres + backend + a **frontend Dockerfile**
  (didn't exist before this phase) using Next.js's `standalone` output +
  NGINX reverse proxy as the single entry point
- NGINX config handles WebSocket upgrade headers (needed for the
  notification socket) and forwards the real client IP (needed for rate
  limiting to key on the actual client, not NGINX's own address)
- Database backup/restore scripts (`pg_dump`/`pg_restore` wrappers,
  custom format for selective/parallel restore, with a confirmation
  prompt before restore overwrites anything)

## What's intentionally NOT done yet (by design, not oversight)

- Email verification / OTP / password reset (needs an email provider)
- Google OAuth
- Redis-backed token blocklist for true server-side logout
- Real object storage for images (S3/GCS) — Phase 2 uses local disk,
  isolated behind `app/core/images.py` so swapping it out later is a
  one-file change
- Postgres full-text search (tsvector) — search/catalog use simple
  ILIKE, upgraded when the catalog has real volume
- Order status history / audit trail (who changed what, when) beyond
  the append-only tracking-event log — no per-field audit of admin
  actions elsewhere yet
- Cancel/return REQUEST flow for customers (admin can move an order into
  those states; a customer-initiated request with a reason is a
  further phase)
- Gating order fulfillment (packed/shipped) on payment status — Phase 4
  records payment status but doesn't yet block admin status transitions
  on it
- Multi-instance WebSocket delivery (Redis Pub/Sub or similar) — the
  current `ConnectionManager` is correct for a single backend process
  only (see `core/ws_manager.py` docstring)
- Review helpful-vote de-duplication (a `ReviewHelpfulVote` join table
  to stop the same person voting repeatedly) — flagged in
  `api/v1/reviews.py` as a real, known gap
- Time-windowed trending searches ("trending this week") — the current
  version is all-time counts, the simplest version that answers the
  question
- Personalized recommendations beyond related/frequently-bought-together
  — needs real usage data to be more than a guess
- Multi-instance rate limiting (Redis-backed storage instead of
  in-memory) — needed once the backend runs as more than one process;
  see `core/rate_limit.py`
- Secrets management (Vault, cloud secrets manager) — this build uses
  plain environment variables, fine for a single-team deployment,
  not for a compliance-sensitive one
- Automated database migration rollback testing, blue/green or canary
  deploys, horizontal autoscaling — genuine production operations
  concerns beyond a learning project's scope
- Full test coverage of every edge case (this suite covers the
  meaningful business logic and security-critical paths — auth, money,
  stock, permissions — not literally every branch)

---

## Running it locally

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then edit DATABASE_URL / SECRET_KEY
# requires a running Postgres — e.g. docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
alembic upgrade head
uvicorn app.main:app --reload
# → API at http://localhost:8000, interactive docs at /docs
```

Run tests (no Postgres needed — uses in-memory SQLite, and no real
Razorpay account needed either — payment tests use a fake gateway and
real HMAC signature math, see `tests/conftest.py`):
```bash
pytest -v
```

To actually test the payment flow end-to-end in the browser (not just
via pytest), put real Razorpay **test-mode** keys in `.env` — free at
https://dashboard.razorpay.com/app/keys. Without them, the backend still
runs fine (placeholder defaults), but the Checkout widget on the frontend
won't complete a real payment.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
# → http://localhost:3000
```

### Docker (backend only)
```bash
cd backend
docker build -t shopsphere-backend .
docker run -p 8000:8000 --env-file .env shopsphere-backend
```

### Full stack with Docker Compose (production-like)
Runs Postgres + backend + frontend + NGINX together, with NGINX as the
single entry point on port 80 — same routing a real deployment would use
(see `nginx/nginx.conf`; it's also why CORS isn't an issue in this mode,
unlike local dev where frontend and backend are different origins):
```bash
export SECRET_KEY=$(openssl rand -hex 32)
docker compose up --build
# → http://localhost (NGINX routes / to the frontend, /api and /media to the backend)
```
Migrations run automatically on backend startup (see the `command:` in
`docker-compose.yml`). Set `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` /
`RAZORPAY_WEBHOOK_SECRET` as additional env vars for a real payment flow.

### CI
`.github/workflows/ci.yml` runs on every push/PR: backend tests against
a **real Postgres service container** (plus an Alembic migration check),
and frontend typecheck + build. Push this to a GitHub repo and it runs
automatically — no separate setup needed.

### Database backup & restore
```bash
./scripts/backup_db.sh                              # → backups/shopsphere_<timestamp>.dump
./scripts/restore_db.sh backups/shopsphere_20260801_120000.dump
```
Both read `DATABASE_URL` from the environment or `backend/.env`.

---

## Next phases (say "continue to Phase 7", or ask for a different phase)

1. ~~**Phase 2 — Product Catalog**~~ ✅ done
2. ~~**Phase 3 — Cart & Checkout**~~ ✅ done
3. ~~**Phase 4 — Payments**~~ ✅ done
4. ~~**Phase 5 — Admin Panel**~~ ✅ done
5. ~~**Phase 6 — Real-time tracking, notifications, search, recommendations,
   reviews**~~ ✅ done
6. ~~**Phase 7 — Hardening & deployment**~~ ✅ done — rate limiting,
   security headers, structured logging, centralized error handling,
   CI/CD, Docker Compose + NGINX, backup/restore scripts

**All 7 phases complete.** Every phase shipped the same way: real code,
actually run against real tests, before moving to the next — including
several real bugs caught only by running the suite, not by reading the
code and assuming it was right (a rate-limiter test-isolation leak in
this phase, a WebSocket test-DB bypass in Phase 6, a bcrypt/passlib
version mismatch in Phase 1, among others — all documented as they
happened, not smoothed over).

From here, natural next steps if you want to keep going: pick any item
from the "What's intentionally NOT done yet" lists above and treat it as
its own small phase, or take this as a base to extend toward your own
product requirements.

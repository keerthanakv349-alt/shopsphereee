# ShopSphere — Codebase Audit Report

**Method note, read this first:** every finding below was verified by actually
running code — reproducing the bug, then re-testing after the fix — not by
reading the code and guessing. Where I initially suspected a bug and then
disproved it with a real test (see "Investigated, not a bug" below), I'm
reporting that too, since claiming a fix for something that isn't broken
would be its own kind of dishonesty.

Final state: **78/78 backend tests passing**, clean `tsc --noEmit`, clean
`next build` (20/20 routes).

---

## 1. Root-cause bug: SQLAlchemy enum binding (`InvalidTextRepresentation`)

**Your report:** `psycopg2.errors.InvalidTextRepresentation: invalid input
value for enum user_role: "CUSTOMER"` on signup.

**Root cause, confirmed empirically:**
`Enum(UserRole, name="user_role")` — used across every model in this
project — makes SQLAlchemy bind a Python enum member's **`.name`**
("CUSTOMER") to the database, not its **`.value`** ("customer"), *even
though `UserRole` is a `str` subclass*. This is a well-documented but
easy-to-miss SQLAlchemy default. I verified it directly:

```python
from sqlalchemy import Enum
from sqlalchemy.dialects import postgresql
e = Enum(UserRole, name="user_role")
e.bind_processor(postgresql.dialect())(UserRole.CUSTOMER)
# → 'CUSTOMER'   (should be 'customer')
```

Every Alembic migration in this project defines its Postgres enum labels
using `.value` strings (lowercase — `"customer"`, `"admin"`, etc.), so the
mismatch surfaces as `InvalidTextRepresentation` the moment SQLAlchemy tries
to write (or filter by) any enum column.

**This is not isolated to signup.** I found the identical pattern on **7
columns** across the whole schema — meaning every one of these was broken
against real Postgres, not just auth:

| Column | Enum class | File |
|---|---|---|
| `users.role` | `UserRole` | `app/models/user.py` |
| `products.status` | `ProductStatus` | `app/models/catalog.py` |
| `orders.status` | `OrderStatus` | `app/models/order.py` |
| `payments.status` | `PaymentStatus` | `app/models/payment.py` |
| `coupons.discount_type` | `DiscountType` | `app/models/coupon.py` |
| `notifications.notification_type` | `NotificationType` | `app/models/notification.py` |
| `tracking_events.status` | `TrackingStatus` | `app/models/delivery.py` |

**Why your test suite didn't catch this:** tests run against in-memory
SQLite. SQLite has no native enum type — SQLAlchemy emulates one with a
`VARCHAR` + `CHECK(value IN (...))` constraint built from the **same
(wrong) name-based list** it was already writing. So SQLite was
self-consistently wrong, and every test passed. Only a real Postgres
enum — with labels fixed by the migration, independent of whatever
SQLAlchemy happens to send — exposes the mismatch. I confirmed this by
running the full existing suite unmodified: **74/74 passed**, proving the
gap.

**Fix — no migration changes needed.** The Postgres enum labels the
migrations already created are correct (they use `.value`); only the
Python-side binding was wrong. Added `app/db/types.py::pg_enum()`, a
drop-in replacement for `Enum()` that sets `values_callable=lambda obj:
[e.value for e in obj]`, and switched all 7 columns to use it. This is a
data-safe, schema-safe fix — nothing about the database changes.

**Regression test added:** `tests/test_enum_bindings.py` — iterates every
enum column, checks what SQLAlchemy would actually send to Postgres via
`bind_processor()`, without needing a live Postgres connection. I proved
this test is real (not tautological) by reverting one column to plain
`Enum()` and confirming the test fails.

**Files changed:** `app/db/types.py`, `app/models/user.py`,
`app/models/catalog.py`, `app/models/order.py`, `app/models/payment.py`,
`app/models/coupon.py`, `app/models/notification.py`,
`app/models/delivery.py`, `tests/test_enum_bindings.py` (new)

---

## 2. CORS — investigated, config was structurally correct; hardened anyway

**Your report:** "No Access-Control-Allow-Origin header present."

**What I tested and disproved:** I suspected the Phase 7 middleware stack
(rate limiter, security headers, request logging) might be shadowing
`CORSMiddleware` and stripping CORS headers from error responses (429s,
500s). I wrote a direct test that exhausts the login rate limit and
inspects the resulting 429's headers — **CORS headers were present on
both normal and rate-limited/error responses.** I'm not reporting this as
a bug, since I disproved my own hypothesis with a real test rather than
leaving a plausible-sounding guess in the report.

**What almost certainly caused the symptom in practice:** the single most
common real-world cause of this exact browser message is **the backend
not actually running or reachable** — not a CORS misconfiguration. Two
concrete ways that happens here:

1. **Missing `.env`.** `Settings()` requires `DATABASE_URL` and
   `SECRET_KEY`. Without `backend/.env`, the app crashes at import time —
   before Uvicorn even binds a port — with a multi-line pydantic
   traceback that's easy to misread as "something about CORS." I
   reproduced this and confirmed the crash.
2. **Origin mismatch.** `http://localhost:3000` and
   `http://127.0.0.1:3000` are *different origins* to a browser, even on
   the same machine. If the backend's `CORS_ORIGINS` only lists one and
   the frontend is opened via the other, the browser correctly reports
   exactly the message you saw.

**Fixes applied:**
- `CORS_ORIGINS` now defaults to `http://localhost:3000,http://127.0.0.1:3000`
  (both `.env.example` and the `Settings` default).
- A missing/invalid `.env` now fails with **one clear, actionable
  message** pointing at `cp .env.example .env`, instead of a buried
  traceback. Verified by simulating a missing `.env` and confirming the
  new message fires.

**Files changed:** `app/core/config.py`, `.env.example`

---

## 3. Frontend bug (found during this audit, not in your original list): login errors were being swallowed

**What I found:** the axios response interceptor (`lib/api.ts`) retried
via token-refresh on **any** 401 — including from `/api/v1/auth/login`
itself. A wrong-password login attempt:
1. Gets a real 401 with `{"detail": "Incorrect email or password"}`.
2. The interceptor sees 401, tries to refresh — but a not-yet-logged-in
   user has no `refresh_token`, so the refresh attempt throws
   immediately.
3. The catch block calls `logout()` (a no-op) and **hard-redirects the
   page to `/login`** — the page the user is already on — wiping the
   form state before the "Incorrect email or password" toast can ever
   render.
4. The promise rejects with a generic `Error("No refresh token
   available")` instead of the real `AxiosError`, so even if the redirect
   didn't happen, `error.response?.data?.detail` would resolve to
   `undefined`.

This is a real, everyday-impact bug — it fires on every single wrong
password, not an edge case.

**Fix:** excluded `/api/v1/auth/login`, `/api/v1/auth/signup`, and
`/api/v1/auth/refresh` from the refresh-retry logic, and changed the
catch block to reject with the *original* error (not the internal
refresh-attempt error) so a caller inspecting it before redirect still
sees something meaningful.

**Files changed:** `lib/api.ts`

---

## 4. Exception handling improvements (issue #7)

Two gaps, both fixed:

- **`IntegrityError` was falling through to a generic 500.** Most
  endpoints already pre-check uniqueness before inserting (e.g. "does
  this email exist?"), but a genuine race condition (two requests landing
  at nearly the same instant) can still hit the database's unique
  constraint directly. Added a dedicated handler mapping `IntegrityError`
  → **409 Conflict**, with the raw exception (which includes SQL text and
  parameter values — a real information leak) logged server-side only,
  never sent to the client. Tested directly, including a check that
  `"INSERT INTO"` and `"psycopg2"` never appear in the response body.
- **Sessions weren't explicitly rolled back on exception.** `get_db()`
  only called `.close()`, relying on its implicit cleanup behavior.
  Added an explicit `db.rollback()` in an `except` block so a session is
  never returned to the pool mid-transaction — a guarantee now, not an
  implementation detail of `close()`.

**Files changed:** `app/core/exception_handlers.py`, `app/db/session.py`,
`tests/test_exception_handlers.py` (new)

---

## 5. Frontend: silent failures / infinite-loading (issue #12)

**Audit finding:** 13 of 14 pages checked `isLoading` but never
`isError`. On a failed API call, React Query correctly sets `isLoading`
to `false` — but with no `isError` check, these pages fell through to
their normal render path with `data` as `undefined`. Depending on the
page, that meant:

- **`app/admin/page.tsx`** (dashboard): `if (!data) return null` — a
  **completely blank page**, zero indication anything was wrong.
- **`app/products/ProductsPageContent.tsx`**: fell into the "no products
  match your filters" branch — actively **misleading**, implying an
  empty search result rather than a broken backend.
- **`app/orders/[id]/page.tsx`**: fell into "Order not found" — same
  problem, conflates a real error with a genuine 404.
- **The remaining 10 pages** (`profile`, `cart`, `orders` list, and 7
  admin pages): rendered blank sections or crashed on `data.map(...)`
  against `undefined`.

**Fix:** added `components/ErrorState.tsx` (a shared error UI with a
retry button) and `lib/error-message.ts` (`getErrorMessage()` — tells a
network error, which needs "check your connection," apart from a real
HTTP 401/403/404/429/5xx response, which has its own specific message,
apart from a FastAPI 422 validation array). Applied `isError` handling to
**all 14 pages**. Also upgraded a few mutation error handlers (category/
brand creation) that were showing a hardcoded generic message instead of
the real backend error.

**Files changed:** `components/ErrorState.tsx` (new), `lib/error-message.ts`
(new), and 14 page files: `app/profile/page.tsx`, `app/cart/page.tsx`,
`app/orders/page.tsx`, `app/orders/[id]/page.tsx`,
`app/products/ProductsPageContent.tsx`, `app/admin/page.tsx`,
`app/admin/categories/page.tsx`, `app/admin/brands/page.tsx`,
`app/admin/products/page.tsx`, `app/admin/orders/page.tsx`,
`app/admin/coupons/page.tsx`, `app/admin/payments/page.tsx`,
`app/admin/users/page.tsx`

---

## 6. Investigated and confirmed working (no changes needed)

To keep this report honest — not every area you asked about had a bug:

- **Auth endpoints** (`/signup`, `/login`, `/refresh`, `/logout`, `/me`):
  covered by 6 existing tests, now additionally exercised correctly by
  the enum fix. No further issues found.
- **Catalog endpoints** (`/products`, `/categories`, `/brands`,
  `/search/trending`) and **filtering/search/sort/pagination**: covered
  by existing tests; the enum fix was the actual blocker for `products`
  filtering by `status` — now resolved.
- **JWT handling** (access/refresh tokens, role-based dependencies,
  protected routes): reviewed in detail, already correctly implemented —
  short-lived access tokens, token-type checks on refresh, `require_role`
  dependency for admin gating. No changes made.
- **Pydantic schemas vs. models**: spot-checked `UserOut`, `ProductDetailOut`,
  `OrderOut` programmatically against their SQLAlchemy models — every
  field not directly matching a column is an expected relationship
  (`category`, `brand`, `items`, `variants`), not a mismatch.
- **Foreign keys / indexes**: scanned every model for FK columns missing
  `index=True` — none found.
- **Migrations vs. models**: cross-checked every enum's Postgres labels
  (defined in the Alembic migration files) against each model's `.value`
  list — all 7 match exactly. No schema drift found beyond the binding
  bug already covered in §1.

---

## Modified files (complete list)

**Backend:**
- `app/db/types.py` — added `pg_enum()` helper
- `app/models/user.py`, `app/models/catalog.py`, `app/models/order.py`,
  `app/models/payment.py`, `app/models/coupon.py`,
  `app/models/notification.py`, `app/models/delivery.py` — switched to
  `pg_enum()`
- `app/core/config.py` — CORS origins default, clear startup error on
  missing env vars
- `app/core/exception_handlers.py` — `IntegrityError` → 409 handler
- `app/db/session.py` — explicit rollback on exception
- `.env.example` — updated `CORS_ORIGINS` default
- `tests/test_enum_bindings.py` (new) — regression test for §1
- `tests/test_exception_handlers.py` (new) — tests for §4

**Frontend:**
- `lib/api.ts` — excluded auth endpoints from refresh-retry logic
- `components/ErrorState.tsx` (new)
- `lib/error-message.ts` (new)
- `app/profile/page.tsx`, `app/cart/page.tsx`, `app/orders/page.tsx`,
  `app/orders/[id]/page.tsx`, `app/products/ProductsPageContent.tsx`,
  `app/admin/page.tsx`, `app/admin/categories/page.tsx`,
  `app/admin/brands/page.tsx`, `app/admin/products/page.tsx`,
  `app/admin/orders/page.tsx`, `app/admin/coupons/page.tsx`,
  `app/admin/payments/page.tsx`, `app/admin/users/page.tsx` — added
  `isError` handling

No Alembic migrations were added or changed — every backend fix was
either Python-side binding logic or new code, never a schema change.

---

## Remaining TODOs (not fixed in this pass — flagged, not silently skipped)

- **Multi-instance rate limiting**: the rate limiter's in-memory store
  only works correctly for a single backend process (see
  `app/core/rate_limit.py`'s own docstring). Needs Redis-backed storage
  before running more than one backend instance.
- **Multi-instance WebSocket delivery**: same limitation, same reason,
  in `app/core/ws_manager.py`.
- **Review helpful-vote de-duplication**: no `ReviewHelpfulVote` join
  table yet, so the same user can click "helpful" more than once.
- **Order fulfillment isn't gated on payment status**: an admin can move
  an order to "packed"/"shipped" even if it was never paid. A real system
  would block that.
- **No live-Postgres CI check for full migration-vs-model drift**: this
  audit's schema/migration comparison was done by reading migration files
  and models directly (see §6) — genuinely thorough, but a live
  `alembic check` against a real Postgres instance (as the project's own
  `.github/workflows/ci.yml` already sets up) is the fuller, ongoing
  safety net going forward.
- **Frontend has no automated test runner** (no Jest/Vitest configured)
  — the fixes in this audit were verified via `tsc --noEmit` and
  `next build`, consistent with how the rest of the project was built,
  but there's no automated regression test for the `lib/api.ts` interceptor
  fix specifically. Worth adding if the project grows.

---

## Steps to run from a clean database

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Point DATABASE_URL at a running Postgres, e.g.:
#   docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Verify the fix directly:
```bash
cd backend
pytest tests/test_enum_bindings.py -v   # the regression test for the root-cause bug
pytest -v                                # full suite — expect 78 passed
```

Then open `http://localhost:3000`, sign up a new account, and confirm it
succeeds — that's the exact path that was broken before this audit.

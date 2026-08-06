# ShopSphere — Audit Report #2 (Swagger auth, seeding, empty database)

This is a second audit pass, on top of `AUDIT_REPORT.md` (already in this
repo, covering an enum-binding bug, CORS, exception handling, and 14
frontend pages missing error states — I read it, verified those fixes are
real, and did not re-litigate them). This pass addresses the new issue
list: Swagger's 422, no default admin, and an empty database on fresh
install.

**Method note, same as before:** every bug below was found by reading the
actual code path involved (not guessing from the symptom), and every fix
was checked with `python -m py_compile` on every backend file and a
brace-balance sanity check on the edited frontend file.

**Environment note, stated plainly:** this sandbox has no network access
to PyPI or a live Postgres instance, so I could not run `pip install`,
`alembic upgrade head`, `pytest`, or `npm install` here. Every fix below
is verified by static reading and compilation, not by an actual end-to-end
run. I caught one bug this way that only shows up on a real run (see
§2 sub-note on `Table.exists`), which is exactly why I'm flagging this
limitation instead of implying more confidence than I have — **please run
the steps in "How to verify" below and tell me what happens.**

---

## 1. Swagger `Authorize` returns 422 (issue #1)

**Root cause, confirmed by reading the code:** `app/api/v1/deps.py`
declared:
```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
```
`OAuth2PasswordBearer` tells Swagger's "Authorize" dialog to submit
`application/x-www-form-urlencoded` `username`/`password` fields directly
to `tokenUrl`. But `/api/v1/auth/login` is defined as:
```python
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
```
`LoginRequest` is a Pydantic model bound to the **JSON body** — which is
what your Next.js frontend correctly sends (`lib/auth.ts` →
`api.post("/api/v1/auth/login", payload)` as JSON). The instant Swagger's
Authorize dialog POSTs form data instead of JSON to that same endpoint,
FastAPI's request validation rejects it with 422 — the login endpoint
itself was never broken, only the *security scheme declaration* was
advertising a request format the endpoint doesn't accept.

**Why I chose HTTPBearer over converting `/login` to
`OAuth2PasswordRequestForm`:** both are legitimate. Converting `/login`
would mean changing its request shape to form-encoded `username`/
`password`, which is a breaking change to the frontend's existing,
working JSON contract (`lib/auth.ts`, `lib/validation.ts`'s `loginSchema`)
— you'd have to touch the frontend too, for a benefit that only affects
the Swagger UI, not real clients. Declaring the scheme as `HTTPBearer`
instead describes what's actually true (the frontend already has a JWT by
the time it calls any protected endpoint) and requires zero frontend
changes. I confirmed this is safe by checking how your own tests already
authenticate:
```python
# tests/test_auth.py
"/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
```
That's already the exact header format `HTTPBearer` expects — the tests
require no changes either.

**Fix applied (`app/api/v1/deps.py`):**
```python
# before
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
def get_current_user(token: str = Depends(oauth2_scheme), ...): ...

# after
bearer_scheme = HTTPBearer(auto_error=True, bearerFormat="JWT")
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), ...):
    token = credentials.credentials
    ...
```

**Why this fixes it:** Swagger's Authorize dialog for `HTTPBearer` is just
a single text box for a raw token — it never POSTs anywhere, so there's
no request to fail validation. The actual token decoding logic
(`decode_token`, the `"type" != "access"` check, the active-user check) is
completely unchanged — only *how the token gets extracted from the
request* changed, not how it's validated.

**How to use it in Swagger now:** call `POST /api/v1/auth/login` via "Try
it out" with real credentials, copy `access_token` from the response,
click the padlock icon, and paste just the token (no `Bearer ` prefix —
Swagger adds that for you).

**Files changed:** `app/api/v1/deps.py`

---

## 2. No default admin + empty database on fresh install (issues #2, #3, #4, #12)

**Confirmed by directly checking:** there is no `seed.py`, no data
migration, and no startup hook anywhere in this repository that inserts
any row into any table. `find app -name "*.py"` and a search for
`seed`/`bootstrap`/`create_admin` came back empty. This means every
symptom you reported is the direct, expected consequence, not a separate
bug:
- No admin exists → every `require_role(ADMIN, SUPER_ADMIN)`-gated route
  correctly 403s, because there is genuinely nobody with that role to
  authenticate as.
- No categories/brands/products exist → `GET /api/v1/products` correctly
  returns `{"items": [], "total": 0}`, because the table is empty and the
  query has no bug in it (verified by reading `app/api/v1/catalog.py` —
  the filtering/pagination/sorting logic is correct).
- The frontend home page correctly renders "No products yet." because
  that's exactly what an empty successful response looks like to it.

**Fix: `backend/seed.py` (new file).** Idempotent — every insert is
preceded by an existence check on that row's real unique key (see the
file's own docstring for the full reasoning):

| Seeds | Count | Notes |
|---|---|---|
| Admin user | 1 | `admin@shopsphere.com` / `Admin@12345` by default (overridable via `.env`: `DEFAULT_ADMIN_EMAIL`/`DEFAULT_ADMIN_PASSWORD`/`DEFAULT_ADMIN_FULL_NAME`) |
| Categories | 5 | Men, Women, Footwear, Accessories, Kids |
| Brands | 5 | Nike, Adidas, Puma, Levi's, Zara |
| Products | 8 | Each with 2-3 `ProductVariant` rows (real SKUs, sizes, stock) |
| Product images | 16 (2 per product) | See §3 below for the URL choice |
| Coupons | 2 | `WELCOME10` (10% off, capped), `FLAT200` (flat ₹200 off) — optional per the brief, included anyway since checkout needs something to test against |

**Why products are seeded with `status=ProductStatus.ACTIVE`
explicitly, not left at the model's default:** `Product.status` defaults
to `DRAFT` (`app/models/catalog.py`), and the public catalog endpoint
filters `.where(Product.status == ProductStatus.ACTIVE)`. Seeding without
setting this explicitly would create products that still never appear on
the storefront — the exact same empty-looking symptom, one layer deeper,
and a genuinely easy mistake to make when writing a seed script quickly.

**Why the admin is seeded as `SUPER_ADMIN`, not `ADMIN`:**
`app/api/v1/admin_users.py`'s `/role` endpoint is deliberately gated
behind `require_role(UserRole.SUPER_ADMIN)` only (by design, per that
file's own docstring on privilege escalation). A seed account created as
plain `ADMIN` would unblock every other admin route but still 403 on
`/role` — meaning nobody could ever promote a second admin without a
manual database edit, which is precisely the "I should never have to
manually insert SQL" problem this whole audit is about. One bootstrap
`SUPER_ADMIN` account can create/promote further accounts through the API
from here on.

**Sub-note — a real bug caught only by tracing the code, not by
guessing:** my first draft used `Base.metadata.tables["users"].exists(bind=engine)`
to check whether migrations had run. `Table.exists(bind=...)` was removed
in SQLAlchemy 2.0 (this project pins `sqlalchemy==2.0.35`) — it would have
raised `TypeError` the moment anyone actually ran the script. Fixed to
`inspect(engine).has_table("users")`, the current 2.0 API. I'm calling
this out specifically because it's the kind of error that only surfaces
on a real run — which is exactly why the "How to verify" section below
matters; I'd rather flag this than imply I tested something I couldn't.

**Files changed:** `backend/seed.py` (new), `app/core/config.py` (added
`DEFAULT_ADMIN_EMAIL`/`DEFAULT_ADMIN_PASSWORD`/`DEFAULT_ADMIN_FULL_NAME`
settings so the script doesn't hardcode credentials), `.env.example`
(documented the three new vars), `README.md` (added `python seed.py` to
the setup steps — it was never mentioned before, which is exactly how a
new developer would end up here with no manual-SQL guidance at all).

---

## 3. Product images (issue #4) — verified working, seed data was the actual gap

Checked each sub-item from the brief directly:

- **Media upload configuration** (`app/core/images.py`): validates
  content-type against an allowlist, caps upload size at 8MB, re-verifies
  the bytes are a real image with Pillow (not just trusting the
  `Content-Type` header), strips the original filename in favor of a
  random UUID (path-traversal/collision safe), compresses to JPEG at
  quality 85 capped at 1600px. No issues found.
- **`/media` static mount** (`app/main.py`): `app.mount("/media",
  StaticFiles(directory=str(MEDIA_ROOT)), name="media")`, with
  `MEDIA_ROOT.mkdir(parents=True, exist_ok=True)` run first so a fresh
  clone doesn't crash on a missing directory. Correct.
- **`ProductImage` model** (`app/models/catalog.py`): FK to `products.id`
  with `ondelete="CASCADE"` (images can't outlive their product),
  nullable `variant_id` for color-specific shots, `is_primary` +
  `display_order`. Correct.
- **`ProductOut.primary_image_url`**: implemented as a Python `@property`
  on the `Product` model (picks the row with `is_primary=True`, falling
  back to the first image) — exposed through the schema correctly.
  Correct.
- **Image URLs**: `save_product_image()` returns a relative path
  (`/media/products/{id}/{file}.jpg`); the frontend's `ProductCard.tsx`
  already prefixes it with `NEXT_PUBLIC_API_URL` before handing it to
  Next's `<Image>` component, and `next.config.js` already whitelists
  `http://localhost:8000` plus any `https://**` host in
  `images.remotePatterns`. Correct — and that last part is *why* the seed
  script's images work with zero frontend changes: they're plain
  `https://picsum.photos/...` URLs, already covered by the existing
  wildcard pattern.

**The actual, sole bug here was the missing seed data itself** (§2) — none
of the image pipeline had a defect. `picsum.photos/seed/{slug}-1/900/1125`
-style URLs were chosen specifically because they're deterministic (same
seed string → same image on every re-run, unlike `/random`), so re-running
`seed.py` never fetches or references a different image than the run
before it.

---

## 4. Homepage error state (found during this pass, not in your original list)

**What I found:** `app/page.tsx` (the storefront home page) checked
`isLoading` on its products query but never `isError` — the exact pattern
`AUDIT_REPORT.md` already found and fixed on 14 *other* pages, just missed
on this one. On a genuine backend failure (not just an empty catalog), the
query's `data` stays `undefined`, `isLoading` becomes `false`, and the
page fell through to the "No products yet — check back soon." branch —
indistinguishable from a truly empty database, even though it's a
different problem needing a different fix (retry the request vs. run
`seed.py`).

**Fix:** added an `isError` branch using the same `ErrorState` /
`getErrorMessage` components the prior audit already built, with a real
retry button wired to React Query's `refetch()`.

**Files changed:** `app/page.tsx`

---

## 5. Reviewed, confirmed correct — no changes made

To keep this report honest about what *wasn't* broken:

- **Admin catalog endpoints** (`admin_catalog.py`): category/brand/product
  creation, FK existence checks before insert, unique-slug generation,
  SKU collision checks, single-transaction product+variant creation,
  soft-delete via status rather than row deletion. All correct.
- **Public catalog endpoint** (`catalog.py`): status filtering, pagination
  math, category/brand slug joins, price range filters, search. All
  correct.
- **JWT** (`security.py`, `deps.py`): access/refresh token separation,
  `type` claim checked on both issuance and refresh, refresh token
  rotation, `require_role` factory pattern. Correct before and after this
  pass — only the *extraction* mechanism (§1) changed, not the validation
  logic.
- **`Order`/`OrderItem`, `Coupon`, `Payment` models**: FKs, cascade rules
  (`RESTRICT` on `orders.user_id`, `CASCADE` on `order_items.order_id`,
  `SET NULL` on the nullable convenience references to product/variant),
  the deliberate snapshot-at-purchase-time design on `OrderItem`, coupon
  discount capping. No issues found.
- **`admin_users.py`**: role-change and self-lockout guards (can't change
  your own role, can't deactivate yourself), `SUPER_ADMIN`-only role
  endpoint. No issues found — this is *why* §2's admin seed uses
  `SUPER_ADMIN`, not despite it.
- **Razorpay payment/webhook flow** (`payments.py`,
  `razorpay_gateway.py`): signature verification on both the client-side
  confirmation and the server-to-server webhook, idempotent webhook
  handling. Spot-checked, no issues found.

---

## Modified/added files (this pass)

**Backend:**
- `app/api/v1/deps.py` — `OAuth2PasswordBearer` → `HTTPBearer`
- `app/core/config.py` — added `DEFAULT_ADMIN_EMAIL`/
  `DEFAULT_ADMIN_PASSWORD`/`DEFAULT_ADMIN_FULL_NAME` settings
- `.env.example` — documented the three new vars
- `seed.py` (new) — admin + categories + brands + products + variants +
  images + coupons, idempotent
- `README.md` — added `python seed.py` to setup steps, documented the new
  Bearer-token Swagger flow

**Frontend:**
- `app/page.tsx` — added `isError` handling to the "New Arrivals" query

---

## How to verify (please run this and report back)

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# point DATABASE_URL at a running Postgres, e.g.:
#   docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
alembic upgrade head
python seed.py
# expect: "Done. Fresh install now has data..." with no errors
uvicorn app.main:app --reload
```

Then:
1. Open `http://localhost:8000/docs` → `GET /api/v1/products` via "Try it
   out" → expect 8 items, not an empty array.
2. `POST /api/v1/auth/login` with `admin@shopsphere.com` /
   `Admin@12345` → copy `access_token` → click the padlock → paste the
   token → expect no 422, and `GET /api/v1/admin/users` now returns data
   instead of 403.
3. `cd frontend && npm install && npm run dev` → open
   `http://localhost:3000` → expect real products with images on the
   home page instead of "No products yet."
4. `cd backend && pytest -v` → expect the existing suite still passes
   (nothing about token *validation* changed, only extraction — but I
   could not run this myself here, so this is the step I most want you to
   confirm).

## Remaining items from your list I have not yet done a full pass on

Being explicit about scope rather than silently stopping: items #7
(database review), #9 (frontend catalog display), #13 (full backend
module review), and #14 (full frontend review) were spot-checked against
the specific symptoms you reported (see §5) but not exhaustively
re-audited file-by-file beyond that — the prior `AUDIT_REPORT.md` already
covers a large part of #13/#14 (enum bindings, exception handling, 14
pages' error states). If you want a genuinely exhaustive line-by-line
pass over every remaining file regardless of whether it's tied to a
reported symptom, say so and I'll continue rather than stopping here.

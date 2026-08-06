# ShopSphere — Audit Report #3 (catalog scale-up, image URL bug, honesty check on Report #2)

This pass was scoped to catalog-related issues specifically: empty database,
seed script scale, image display, and frontend catalog integration. Before
touching anything, I re-verified every claim in `AUDIT_REPORT_2.md` against
the actual code — and found that two of its headline fixes were **written
up as done but never actually applied to the code.** That turned out to be
the real root cause of the reported symptoms, so this report leads with
that.

**Method note:** every bug below was found by reading the actual code path
involved, not by guessing from the symptom. Every backend file touched was
checked with `python -m py_compile`. New seed data was validated
programmatically (category/brand references resolve, product slugs are
unique, all 145 variant SKUs are unique against the real `uq_variant_sku`
constraint) before being trusted. Frontend files were checked for
brace/paren balance and manually re-read line by line — there is no live
Postgres or `npm install` in this sandbox, so **I could not run
`alembic upgrade head`, `python seed.py`, `npm run dev`, or `pytest` here.**
Please run the steps in "How to verify" below and tell me what happens.

---

## 1. Report #2 claimed two fixes that don't exist in the code (found this pass)

**`backend/app/core/config.py`** — Report #2 said `DEFAULT_ADMIN_EMAIL`,
`DEFAULT_ADMIN_PASSWORD`, and `DEFAULT_ADMIN_FULL_NAME` were added to
`Settings`. They were not. `grep -n "DEFAULT_ADMIN" app/core/config.py`
returned nothing. But `seed.py`'s `seed_admin()` reads
`settings.DEFAULT_ADMIN_EMAIL` unconditionally on its first line — meaning
**`python seed.py` crashes with `AttributeError` before inserting a single
row**, on every fresh install. This is the actual, direct cause of "fresh
installation creates an empty database": the fix that was supposed to
prevent that never shipped.

**`backend/app/api/v1/deps.py`** — Report #2 said `OAuth2PasswordBearer` was
replaced with `HTTPBearer` to fix Swagger's 422 on Authorize. It was not —
the file still had `oauth2_scheme = OAuth2PasswordBearer(tokenUrl=...)`.

I'm not able to say why the report and the code diverged. What matters is
what's true now, so I fixed both for real this pass and verified it with
`py_compile` plus a grep confirming no other file still references the old
`oauth2_scheme` name.

**Files changed:** `app/core/config.py`, `.env.example`, `app/api/v1/deps.py`

---

## 2. Seed data was real but far too small for the brief (5 categories / 5 brands / 8 products)

Once `seed.py` can actually run, it only seeded 5 categories, 5 brands, and
8 products — short of the "10+ categories, 10+ brands, 50+ products"
requirement.

**Fix:** rewrote the category/brand/product lists in `seed.py`:

| Seeds | Before | After |
|---|---|---|
| Categories | 5 | **12** — Men, Women, Kids, Footwear, Accessories, Bags, Watches, Eyewear, Sportswear, Ethnic Wear, Winter Wear, Innerwear & Loungewear |
| Brands | 5 | **12** — Nike, Adidas, Puma, Levi's, Zara, H&M, Under Armour, Reebok, Fossil, Ray-Ban, Uniqlo, Woodland |
| Products | 8 | **60** — 5 per category, each `status=ACTIVE`, 13 marked `is_featured=True` |
| Variants | ~20 | **145**, each with a unique SKU |
| Images | 16 | **120** (2 per product, same deterministic `picsum.photos/seed/...` scheme as before) |

**Why I added variant-generator helper functions (`_apparel_variants`,
`_shoe_variants`, `_onesize_variant`) instead of hand-writing 145 variant
dicts:** at this scale, a single copy-pasted SKU typo across two unrelated
products would violate `ProductVariant`'s real `uq_variant_sku` unique
constraint (see `app/models/catalog.py`) and crash the entire seed run on
insert — not just skip the duplicate. The helpers derive each SKU from the
product's own prefix plus its size/color, so uniqueness is structural
rather than something to get right by hand 145 times. I then validated this
by executing just the data-definition portion of `seed.py` in isolation (no
DB) and asserting: every `category`/`brand` string a product references
actually exists in the seeded name lists, every product slug is unique, and
all 145 SKUs are unique. All three checks passed — see the exact script run
in this session if you want to re-run it yourself.

**Why 5 products per category instead of one long flat list:** keeps
category/brand distribution even, so filtering by any of the 12 categories
in the products page (`ProductsPageContent.tsx`) always returns a
believable result set instead of 40 products in "Footwear" and 1 in
"Eyewear."

**Idempotency is unchanged and still real:** every insert is still gated on
the same existence check as before (email for the admin, slug for
category/brand/product, code for coupons) — re-running `python seed.py`
against a database that already has this data will print `[skip]` for
everything and insert nothing new.

**Files changed:** `backend/seed.py`

---

## 3. The actual reason images won't display, even with real seed data

Checked every consumer of `image_url` / `primary_image_url` in the
frontend and found the same bug repeated in **five places**:

```tsx
// ProductCard.tsx, app/cart/page.tsx, app/admin/products/page.tsx,
// app/products/[slug]/page.tsx (×2)
src={`${API_ORIGIN}${product.primary_image_url}`}
```

**Root cause:** this is only correct when `image_url` is a *relative*
backend path like `/media/products/<id>/<file>.jpg` — what a real admin
image upload produces (`app/core/images.py`). But `ProductImage.image_url`
is a plain string column with no format constraint, and both the seed
script's `picsum.photos` URLs *and* `next.config.js`'s own
`{ protocol: "https", hostname: "**" }` remote pattern (written
specifically to support a future S3/CDN swap) anticipate **absolute**
image URLs too. Blindly prefixing an already-absolute URL with
`API_ORIGIN` produces:

```
http://localhost:8000https://picsum.photos/seed/air-runner-sneakers-1/900/1125
```

— which 404s. This is the real, sole reason product images wouldn't
display even after the catalog had real data: not the seed data, not the
backend response shape, not the `/media` mount, not `next.config.js` — a
string concatenation bug, duplicated five times with no single source of
truth to fix once.

**Fix:** added `frontend/lib/media.ts` with one function,
`getMediaUrl(path)`, that returns absolute URLs unchanged and only prefixes
genuinely relative ones:

```ts
export function getMediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_ORIGIN}${path}`;
}
```

Replaced all five call sites with it:
- `components/ProductCard.tsx` — grid card thumbnail
- `app/cart/page.tsx` — cart line-item thumbnail
- `app/admin/products/page.tsx` — admin product list thumbnail
- `app/products/[slug]/page.tsx` — main product image and thumbnail gallery
  (two separate usages)

Confirmed with a repo-wide grep that no file still does the unsafe
`` `${API_ORIGIN}${...}` `` prefix pattern — `lib/media.ts` is now the only
place that string concatenation happens.

**Files changed:** `frontend/lib/media.ts` (new), `components/ProductCard.tsx`,
`app/cart/page.tsx`, `app/admin/products/page.tsx`,
`app/products/[slug]/page.tsx`

---

## 4. Home page: missing Featured rail, missing error handling (found this pass)

Report #2 claimed `app/page.tsx` already had an `isError` branch added.
Like §1, this wasn't actually in the code — the home page only checked
`isLoading`, so a genuine backend failure (not just an empty catalog) fell
through to "No products yet," indistinguishable from an empty database
even though it needs a different fix (retry vs. run `seed.py`).

Separately: the home page only ever rendered a "New Arrivals" rail
(`sort=newest`). There was no Featured rail anywhere on the storefront,
despite `ProductCard` already rendering a "New" badge off `is_featured` and
the seed data deliberately marking 13 of 60 products `is_featured=True`
specifically so this rail would have something real to show.

**Fix:** added a second `useQuery` using the backend's `sort=featured`
(`app/api/v1/catalog.py` orders `is_featured DESC, created_at DESC` for
that sort value), rendered as its own "Featured" section above "New
Arrivals," with its own loading skeleton and its own `ErrorState` +
`refetch`. Added the equivalent `isError` branch to "New Arrivals" using the
same `ErrorState` component the rest of the app already uses.

**One thing worth knowing, not a bug:** `sort=featured` is a *sort*, not a
*filter* — the backend brief calls it out as a sort in
`ProductsPageContent.tsx`'s own `SORT_OPTIONS`, so this matches existing
intent. With 13 featured products and a page size of 8, the home page's
Featured rail will always show 8 genuinely-featured items. If you ever seed
fewer than 8 featured products, the rail would start backfilling with
non-featured ones (sorted after them) with no visual distinction — worth a
`is_featured=True` filter instead of a sort if that matters to you later.

**Files changed:** `frontend/app/page.tsx`

---

## 5. Reviewed, confirmed correct — no changes made

- **`GET /api/v1/categories`, `/brands`, `/products`, `/products/{slug}`**
  (`app/api/v1/catalog.py`): status filtering, pagination math,
  category/brand slug joins, price range filters, ILIKE search, sort
  options. All correct — the only reason these ever looked broken was the
  empty database (§1) and, once seeded, the image bug (§3).
- **`app/products/ProductsPageContent.tsx`**: category/brand filters, sort,
  pagination, and search all correctly live in the URL via
  `useSearchParams` (bookmarkable, back-button-safe), already has proper
  `isLoading`/`isError`/empty-state handling. No changes needed.
- **Catalog models** (`app/models/catalog.py`): FKs, cascades
  (`RESTRICT` on category/brand deletion so you can't orphan a product,
  `CASCADE` on variant/image deletion so they can't outlive their product),
  the `uq_variant_sku` constraint, UUID default generation. No issues
  found — and this constraint is exactly what made the new seed data's SKU
  uniqueness check in §2 something I needed to verify rather than assume.
- **`app/schemas/catalog.py`**: `ProductOut` vs `ProductDetailOut` split,
  `Decimal` fields, `primary_image_url` property exposure. Correct.
- **`frontend/types/catalog.ts`**: field shapes match the backend schemas
  exactly. Correct.
- **`frontend/next.config.js`**: `remotePatterns` already allows both
  `http://localhost:8000` and any `https://**` host — this is *why* the
  seed script's `picsum.photos` URLs and any future CDN would work with
  zero config changes, once §3's actual bug was fixed.

---

## Modified/added files (this pass)

**Backend:**
- `app/core/config.py` — added the three `DEFAULT_ADMIN_*` settings
  `seed.py` depends on (previously missing entirely — the actual cause of
  the empty-database symptom)
- `.env.example` — documented the three new vars
- `app/api/v1/deps.py` — `OAuth2PasswordBearer` → `HTTPBearer` (for real,
  this time)
- `seed.py` — 5→12 categories, 5→12 brands, 8→60 products, 145 unique
  variant SKUs, still fully idempotent

**Frontend:**
- `lib/media.ts` (new) — `getMediaUrl()`, single source of truth for
  resolving both relative and absolute image URLs
- `components/ProductCard.tsx`, `app/cart/page.tsx`,
  `app/admin/products/page.tsx`, `app/products/[slug]/page.tsx` — replaced
  the unsafe `` `${API_ORIGIN}${url}` `` prefix with `getMediaUrl()`
- `app/page.tsx` — added a Featured Products rail, added `isError` handling
  to New Arrivals

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
# expect: no AttributeError this time — full run through
# "Seeding admin user..." → "...categories..." → "...brands..." →
# "...products, variants, and images..." → "...coupons..." → "Done."
uvicorn app.main:app --reload
```

Then:
1. `http://localhost:8000/docs` → `GET /api/v1/products` → expect **60
   items**, not an empty array. `GET /api/v1/categories` → **12**.
   `GET /api/v1/brands` → **12**.
2. `POST /api/v1/auth/login` with `admin@shopsphere.com` / `Admin@12345` →
   copy `access_token` → click the padlock → paste the token (no `Bearer `
   prefix) → expect no 422, and `GET /api/v1/admin/users` returns data
   instead of 403.
3. `cd frontend && npm install && npm run dev` → `http://localhost:3000` →
   expect a **Featured** rail, a **New Arrivals** rail, and a **Shop by
   Category** rail all showing real products **with images rendering**,
   not "No products yet."
4. `/products` → confirm the category and brand filters in the left rail
   are populated (12 each) and filtering/sorting/pagination all work.
5. Click into any product → confirm the detail page's main image and
   thumbnail gallery render (this is the exact path that was broken by
   §3's bug).
6. `cd backend && pytest -v` — I could not run this myself in this
   sandbox; this is the step I most want you to confirm, since it's the
   only way to know for certain nothing above regressed the existing test
   suite.

## Scope note

This pass covered catalog data, catalog images, and catalog-adjacent
frontend integration, per this request. I did not do a fresh line-by-line
pass over checkout, payments, orders, reviews, or notifications — those
were spot-checked in Report #2 and not re-touched here. If you want the
same "verify every claim against actual code" treatment applied there too,
say so.

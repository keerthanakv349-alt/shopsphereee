# """
# Database seed script — audit items #3 ("Empty Database"), #4 ("Product
# Images"), and #12 ("Seed Script").

# WHY THIS FILE EXISTS AT ALL:
# Before this fix, a fresh `alembic upgrade head` created a schema with zero
# rows in it. That meant: no admin user (so every admin endpoint 403'd —
# there was nothing WITH the admin role to log in as), no categories/brands
# (so the admin UI's "create product" dropdowns were empty), and no
# products/images (so the storefront home page always showed "No products
# yet." and GET /api/v1/products always returned {"items": [], "total": 0}
# on a brand new install). The project's own setup instructions
# (README "Getting Started") never mentioned any manual SQL step — so a new
# developer following them exactly would land on a broken-looking app
# through no fault of their own. This script is the actual fix: it is the
# "proper database seeding system" the audit brief asked for, not a
# suggestion to write one.

# WHY A PLAIN SCRIPT, NOT AN ALEMBIC DATA MIGRATION:
# Schema changes (tables/columns) belong in Alembic migrations because every
# environment must apply them exactly once, in order, forever. Seed DATA is
# different — it's "give me something to develop against," which you often
# want to re-run, skip in CI, or run against a copy of prod for a demo
# environment. Baking sample products into a schema migration would mean
# "alembic upgrade head" inserts fake products into a REAL production
# database the first time someone runs it there. A standalone script that
# an engineer explicitly runs (`python seed.py`) keeps that decision in
# human hands.

# WHY THIS IS SAFE TO RUN MULTIPLE TIMES (idempotency):
# Every insert below is preceded by an existence check on that row's real
# unique key (email for the admin user, slug for categories/brands/products,
# sku for variants, code for coupons) — see `_get_or_create` and the
# per-entity checks. Running `python seed.py` a second time against a
# database that already has this data prints "already exists, skipping"
# for everything and creates nothing new or duplicated. This matters
# because the setup instructions tell every new developer to run this
# script as a normal setup step — it has to be safe if someone runs it
# twice by mistake, or re-runs it after pulling a teammate's migration.

# USAGE:
#     cd backend
#     python seed.py
# """
# from __future__ import annotations

# import sys
# from decimal import Decimal

# from sqlalchemy import inspect

# from app.core.security import hash_password
# from app.db.session import SessionLocal, engine

# # Import every model module so Base.metadata is fully populated before we
# # touch the database — mirrors alembic/env.py's import list exactly, for
# # the same reason (SQLAlchemy needs every mapped class registered before
# # relationships between them can be resolved).
# from app.models.address import Address  # noqa: F401
# from app.models.cart import Cart, CartItem  # noqa: F401
# from app.models.catalog import Brand, Category, Product, ProductImage, ProductStatus, ProductVariant
# from app.models.coupon import Coupon, DiscountType
# from app.models.delivery import DeliveryPartner, TrackingEvent  # noqa: F401
# from app.models.notification import Notification  # noqa: F401
# from app.models.order import Order, OrderItem  # noqa: F401
# from app.models.payment import Payment  # noqa: F401
# from app.models.review import Review  # noqa: F401
# from app.models.search_log import SearchQuery  # noqa: F401
# from app.models.user import User, UserRole
# from app.schemas.catalog import slugify
# from app.core.config import settings


# def seed_admin(db) -> None:
#     """Audit item #2: fresh installs had no ADMIN user at all, so every
#     admin-only endpoint correctly returned 403 — there was no bug in the
#     403 itself, just nobody who was actually allowed in. Existence check
#     is by email (the column the login flow itself keys off of).

#     Seeded as SUPER_ADMIN, not ADMIN: app/api/v1/admin_users.py gates its
#     /role endpoint behind `require_role(UserRole.SUPER_ADMIN)` specifically
#     (by design — see that file's docstring on why role changes are
#     restricted beyond plain ADMIN). A bootstrap account seeded as ADMIN
#     would still 403 on that one route with nobody able to grant SUPER_ADMIN
#     to anyone, ever, without a manual DB edit — exactly the kind of
#     "never touch SQL by hand" violation this whole audit is trying to
#     eliminate. One SUPER_ADMIN seed account can create/promote further
#     ADMIN accounts through the API itself from here on."""
#     existing = db.query(User).filter(User.email == settings.DEFAULT_ADMIN_EMAIL.lower()).first()
#     if existing:
#         print(f"  [skip] admin user '{settings.DEFAULT_ADMIN_EMAIL}' already exists")
#         return

#     admin = User(
#         full_name=settings.DEFAULT_ADMIN_FULL_NAME,
#         email=settings.DEFAULT_ADMIN_EMAIL.lower(),
#         hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
#         role=UserRole.SUPER_ADMIN,
#         is_active=True,
#         is_email_verified=True,
#     )
#     db.add(admin)
#     db.commit()
#     print(f"  [ok] created admin user: {settings.DEFAULT_ADMIN_EMAIL} / {settings.DEFAULT_ADMIN_PASSWORD}")


# CATEGORY_NAMES = [
#     "Men",
#     "Women",
#     "Kids",
#     "Footwear",
#     "Accessories",
#     "Bags",
#     "Watches",
#     "Eyewear",
#     "Sportswear",
#     "Ethnic Wear",
#     "Winter Wear",
#     "Innerwear & Loungewear",
# ]


# def seed_categories(db) -> dict[str, Category]:
#     names = CATEGORY_NAMES
#     result: dict[str, Category] = {}
#     for name in names:
#         slug = slugify(name)
#         existing = db.query(Category).filter(Category.slug == slug).first()
#         if existing:
#             print(f"  [skip] category '{name}' already exists")
#             result[name] = existing
#             continue
#         category = Category(name=name, slug=slug)
#         db.add(category)
#         db.commit()
#         db.refresh(category)
#         result[name] = category
#         print(f"  [ok] created category: {name}")
#     return result


# BRAND_NAMES = [
#     "Nike",
#     "Adidas",
#     "Puma",
#     "Levi's",
#     "Zara",
#     "H&M",
#     "Under Armour",
#     "Reebok",
#     "Fossil",
#     "Ray-Ban",
#     "Uniqlo",
#     "Woodland",
# ]


# def seed_brands(db) -> dict[str, Brand]:
#     names = BRAND_NAMES
#     result: dict[str, Brand] = {}
#     for name in names:
#         slug = slugify(name)
#         existing = db.query(Brand).filter(Brand.slug == slug).first()
#         if existing:
#             print(f"  [skip] brand '{name}' already exists")
#             result[name] = existing
#             continue
#         brand = Brand(name=name, slug=slug)
#         db.add(brand)
#         db.commit()
#         db.refresh(brand)
#         result[name] = brand
#         print(f"  [ok] created brand: {name}")
#     return result


# # Deterministic placeholder photography — picsum.photos returns the SAME
# # image for the same seed string every time (unlike /random), so re-running
# # this script always requests the identical URLs instead of new ones on
# # every run. Using an external image host (rather than files on local
# # disk) means this script needs zero binary assets committed to the repo,
# # and it exercises the exact same ProductImage.image_url / primary_image_url
# # code path a real admin-uploaded image would (see app/core/images.py for
# # the upload path itself, which this intentionally does NOT duplicate —
# # seed data and admin uploads are different write paths by design).
# def _placeholder_image_url(seed: str, width: int = 900, height: int = 1125) -> str:
#     return f"https://picsum.photos/seed/{seed}/{width}/{height}"


# # WHY HELPER FUNCTIONS BUILD THE VARIANT LISTS BELOW, INSTEAD OF WRITING
# # EACH VARIANT DICT BY HAND (like the previous 8-product version did):
# # at 60 products, hand-writing every {"sku": ..., "size": ..., "color": ...,
# # "stock_quantity": ...} risks exactly the kind of copy-paste typo that
# # causes a duplicate SKU across two unrelated products — which would
# # violate ProductVariant's real uq_variant_sku constraint (see
# # app/models/catalog.py) and crash the whole seed run on insert. These
# # three helpers guarantee a unique, deterministic SKU per (product, size,
# # color) combination from the product's own SKU prefix, so uniqueness is
# # structural instead of "please don't typo it."
# def _apparel_variants(prefix: str, sizes: list[str], colors: list[str], base_stock: int = 20) -> list[dict]:
#     variants = []
#     for i, size in enumerate(sizes):
#         color = colors[i % len(colors)]
#         variants.append(
#             {
#                 "sku": f"{prefix}-{size}-{color[:3].upper()}",
#                 "size": size,
#                 "color": color,
#                 "stock_quantity": base_stock + (i * 5),
#             }
#         )
#     return variants


# def _shoe_variants(prefix: str, sizes: list[str], colors: list[str], base_stock: int = 15) -> list[dict]:
#     variants = []
#     for i, size in enumerate(sizes):
#         color = colors[i % len(colors)]
#         variants.append(
#             {
#                 "sku": f"{prefix}-{size}-{color[:3].upper()}",
#                 "size": size,
#                 "color": color,
#                 "stock_quantity": base_stock + (i * 4),
#             }
#         )
#     return variants


# def _onesize_variant(prefix: str, color: str, stock: int = 40) -> list[dict]:
#     return [{"sku": f"{prefix}-ONE-{color[:3].upper()}", "size": None, "color": color, "stock_quantity": stock}]


# PRODUCTS: list[dict] = [
#     # --- Men (5) ---
#     {
#         "name": "511 Slim Fit Jeans",
#         "category": "Men", "brand": "Levi's",
#         "base_price": Decimal("3999.00"), "discount_percentage": Decimal("10.00"),
#         "description": "A slim fit through the seat and thigh with a tapered leg, cut from stretch denim.",
#         "is_featured": True,
#         "variants": _apparel_variants("LEVIS-511", ["30", "32", "34"], ["Indigo", "Black"]),
#     },
#     {
#         "name": "Regular Fit Oxford Shirt",
#         "category": "Men", "brand": "Zara",
#         "base_price": Decimal("2999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A crisp cotton Oxford shirt with a button-down collar, cut for a regular fit.",
#         "is_featured": False,
#         "variants": _apparel_variants("ZARA-OXFORD", ["S", "M", "L"], ["White", "Sky Blue"]),
#     },
#     {
#         "name": "Slim Fit Chino Trousers",
#         "category": "Men", "brand": "H&M",
#         "base_price": Decimal("2499.00"), "discount_percentage": Decimal("5.00"),
#         "description": "Stretch cotton chinos with a slim leg and a comfortable mid-rise waist.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-CHINO", ["30", "32", "34"], ["Khaki", "Navy"]),
#     },
#     {
#         "name": "Airism Crew Neck Tee",
#         "category": "Men", "brand": "Uniqlo",
#         "base_price": Decimal("990.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A moisture-wicking, quick-drying crew neck tee for everyday wear.",
#         "is_featured": True,
#         "variants": _apparel_variants("UNIQLO-AIRISM-M", ["S", "M", "L", "XL"], ["Grey", "Black"]),
#     },
#     {
#         "name": "Dri-FIT Training Tee",
#         "category": "Men", "brand": "Nike",
#         "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Sweat-wicking training tee with a relaxed fit and dropped hem.",
#         "is_featured": False,
#         "variants": _apparel_variants("NIKE-DRIFIT-M", ["M", "L", "XL"], ["Black", "Grey"]),
#     },
#     # --- Women (5) ---
#     {
#         "name": "Satin Wrap Midi Dress",
#         "category": "Women", "brand": "Zara",
#         "base_price": Decimal("3299.00"), "discount_percentage": Decimal("20.00"),
#         "description": "A wrap-front midi dress in fluid satin, finished with a self-tie belt.",
#         "is_featured": True,
#         "variants": _apparel_variants("ZARA-WRAP", ["S", "M", "L"], ["Black", "Wine"]),
#     },
#     {
#         "name": "Ribbed Knit Bodysuit",
#         "category": "Women", "brand": "H&M",
#         "base_price": Decimal("1299.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A fitted ribbed bodysuit with a scoop neck, layers cleanly under blazers.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-BODYSUIT", ["XS", "S", "M"], ["Black", "Ecru"]),
#     },
#     {
#         "name": "Ultra Light Down Vest",
#         "category": "Women", "brand": "Uniqlo",
#         "base_price": Decimal("3990.00"), "discount_percentage": Decimal("10.00"),
#         "description": "A packable down vest with a DWR finish, warm without the bulk.",
#         "is_featured": False,
#         "variants": _apparel_variants("UNIQLO-DOWNVEST-W", ["S", "M", "L"], ["Navy", "Beige"]),
#     },
#     {
#         "name": "501 High Rise Jeans",
#         "category": "Women", "brand": "Levi's",
#         "base_price": Decimal("4299.00"), "discount_percentage": Decimal("0.00"),
#         "description": "The original straight fit, reworked with a high rise for a longer leg line.",
#         "is_featured": False,
#         "variants": _apparel_variants("LEVIS-501-W", ["26", "28", "30"], ["Light Blue", "Black"]),
#     },
#     {
#         "name": "Tailored Single-Breasted Blazer",
#         "category": "Women", "brand": "Zara",
#         "base_price": Decimal("5999.00"), "discount_percentage": Decimal("15.00"),
#         "description": "A structured blazer with a tailored waist, works over both tees and shirts.",
#         "is_featured": True,
#         "variants": _apparel_variants("ZARA-BLAZER-W", ["S", "M", "L"], ["Black", "Camel"]),
#     },
#     # --- Kids (5) ---
#     {
#         "name": "Cotton Graphic Print Tee",
#         "category": "Kids", "brand": "H&M",
#         "base_price": Decimal("799.00"), "discount_percentage": Decimal("0.00"),
#         "description": "100% cotton crew-neck tee with a front graphic print, pre-shrunk fabric.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-KIDTEE", ["4Y", "6Y", "8Y"], ["Red", "Blue"]),
#     },
#     {
#         "name": "Fleece Zip-Up Hoodie",
#         "category": "Kids", "brand": "Uniqlo",
#         "base_price": Decimal("1490.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Soft fleece hoodie with a full front zip, sized for layering.",
#         "is_featured": False,
#         "variants": _apparel_variants("UNIQLO-KIDHOOD", ["6Y", "8Y", "10Y"], ["Grey", "Navy"]),
#     },
#     {
#         "name": "Junior Track Suit Set",
#         "category": "Kids", "brand": "Adidas",
#         "base_price": Decimal("2999.00"), "discount_percentage": Decimal("10.00"),
#         "description": "A matching zip jacket and jogger set in soft-touch fleece.",
#         "is_featured": True,
#         "variants": _apparel_variants("ADIDAS-KIDTRACK", ["6Y", "8Y", "10Y"], ["Navy", "Black"]),
#     },
#     {
#         "name": "Denim Dungaree Overalls",
#         "category": "Kids", "brand": "H&M",
#         "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Adjustable-strap denim overalls with front pocket detail.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-DUNGAREE", ["4Y", "6Y"], ["Blue"]),
#     },
#     {
#         "name": "Junior Running Shoes",
#         "category": "Kids", "brand": "Puma",
#         "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Lightweight running shoes with a hook-and-loop strap for easy wear.",
#         "is_featured": False,
#         "variants": _shoe_variants("PUMA-KIDRUN", ["UK1", "UK2", "UK3"], ["Black", "Red"]),
#     },
#     # --- Footwear (5) ---
#     {
#         "name": "Air Runner Sneakers",
#         "category": "Footwear", "brand": "Nike",
#         "base_price": Decimal("6999.00"), "discount_percentage": Decimal("10.00"),
#         "description": "Lightweight everyday running sneakers with breathable mesh uppers.",
#         "is_featured": True,
#         "variants": _shoe_variants("NIKE-AIRRUN", ["UK7", "UK8", "UK9", "UK10"], ["Black", "White"]),
#     },
#     {
#         "name": "Ultraboost Running Shoes",
#         "category": "Footwear", "brand": "Adidas",
#         "base_price": Decimal("13999.00"), "discount_percentage": Decimal("15.00"),
#         "description": "Responsive Boost midsole with a Primeknit upper for all-day comfort.",
#         "is_featured": True,
#         "variants": _shoe_variants("ADIDAS-ULTRABOOST", ["UK7", "UK8", "UK9"], ["Black", "Grey"]),
#     },
#     {
#         "name": "Cloud Cushion Slides",
#         "category": "Footwear", "brand": "Puma",
#         "base_price": Decimal("1999.00"), "discount_percentage": Decimal("15.00"),
#         "description": "Everyday cushioned slides for post-workout comfort.",
#         "is_featured": False,
#         "variants": _shoe_variants("PUMA-SLIDE", ["UK7", "UK8", "UK9"], ["Grey", "Black"]),
#     },
#     {
#         "name": "Classic Leather Sneakers",
#         "category": "Footwear", "brand": "Reebok",
#         "base_price": Decimal("4499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A timeless low-top leather sneaker with a cupsole and suede accents.",
#         "is_featured": False,
#         "variants": _shoe_variants("REEBOK-CLASSIC", ["UK7", "UK8", "UK9", "UK10"], ["White", "Grey"]),
#     },
#     {
#         "name": "Trek Leather Boots",
#         "category": "Footwear", "brand": "Woodland",
#         "base_price": Decimal("5499.00"), "discount_percentage": Decimal("5.00"),
#         "description": "Rugged full-grain leather boots with a grippy lug outsole for the outdoors.",
#         "is_featured": False,
#         "variants": _shoe_variants("WOODLAND-TREK", ["UK8", "UK9", "UK10"], ["Brown", "Tan"]),
#     },
#     # --- Accessories (5) ---
#     {
#         "name": "Bifold Leather Wallet",
#         "category": "Accessories", "brand": "Fossil",
#         "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A slim bifold wallet in full-grain leather with six card slots.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-WALLET", "Brown", 30) + _onesize_variant("FOSSIL-WALLET", "Black", 30),
#     },
#     {
#         "name": "Reversible Leather Belt",
#         "category": "Accessories", "brand": "Zara",
#         "base_price": Decimal("1499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A reversible belt with a rotating buckle, switches from black to brown.",
#         "is_featured": False,
#         "variants": _apparel_variants("ZARA-BELT", ["M", "L"], ["Black/Brown"]),
#     },
#     {
#         "name": "Ribbed Wool Beanie",
#         "category": "Accessories", "brand": "H&M",
#         "base_price": Decimal("699.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A snug ribbed-knit beanie in a soft wool blend.",
#         "is_featured": False,
#         "variants": _onesize_variant("HM-BEANIE", "Charcoal", 50),
#     },
#     {
#         "name": "Curb Chain Bracelet",
#         "category": "Accessories", "brand": "Fossil",
#         "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A stainless steel curb-chain bracelet with a lobster clasp.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-BRACELET", "Silver", 25),
#     },
#     {
#         "name": "Printed Silk Scarf",
#         "category": "Accessories", "brand": "Zara",
#         "base_price": Decimal("1299.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A lightweight printed scarf in silk-blend fabric.",
#         "is_featured": False,
#         "variants": _onesize_variant("ZARA-SCARF", "Multicolor", 35),
#     },
#     # --- Bags (5) ---
#     {
#         "name": "Everyday Structured Tote Bag",
#         "category": "Bags", "brand": "Zara",
#         "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A structured tote in vegan leather, sized for a 13-inch laptop.",
#         "is_featured": False,
#         "variants": _onesize_variant("ZARA-TOTE", "Tan", 50),
#     },
#     {
#         "name": "Canvas Travel Backpack",
#         "category": "Bags", "brand": "Woodland",
#         "base_price": Decimal("3499.00"), "discount_percentage": Decimal("10.00"),
#         "description": "A durable canvas backpack with a padded laptop sleeve and leather trims.",
#         "is_featured": True,
#         "variants": _onesize_variant("WOODLAND-BACKPACK", "Olive", 22) + _onesize_variant("WOODLAND-BACKPACK", "Black", 22),
#     },
#     {
#         "name": "Quilted Crossbody Bag",
#         "category": "Bags", "brand": "H&M",
#         "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A compact quilted crossbody with an adjustable chain strap.",
#         "is_featured": False,
#         "variants": _onesize_variant("HM-CROSSBODY", "Black", 40),
#     },
#     {
#         "name": "Leather Messenger Bag",
#         "category": "Bags", "brand": "Fossil",
#         "base_price": Decimal("4999.00"), "discount_percentage": Decimal("5.00"),
#         "description": "A full-grain leather messenger bag with a padded 15-inch laptop compartment.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-MESSENGER", "Cognac", 15),
#     },
#     {
#         "name": "Mini Shoulder Bag",
#         "category": "Bags", "brand": "Zara",
#         "base_price": Decimal("2199.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A compact shoulder bag with a detachable chain strap.",
#         "is_featured": False,
#         "variants": _onesize_variant("ZARA-MINIBAG", "Black", 28),
#     },
#     # --- Watches (5) ---
#     {
#         "name": "Gen 6 Smartwatch",
#         "category": "Watches", "brand": "Fossil",
#         "base_price": Decimal("22995.00"), "discount_percentage": Decimal("10.00"),
#         "description": "A Wear OS smartwatch with heart-rate tracking and a silicone strap.",
#         "is_featured": True,
#         "variants": _onesize_variant("FOSSIL-GEN6", "Black", 18),
#     },
#     {
#         "name": "Grant Chronograph Watch",
#         "category": "Watches", "brand": "Fossil",
#         "base_price": Decimal("12995.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A chronograph dial watch on a genuine leather strap.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-GRANT", "Brown", 20),
#     },
#     {
#         "name": "Neutra Minimalist Watch",
#         "category": "Watches", "brand": "Fossil",
#         "base_price": Decimal("9995.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A slim-case minimalist watch with a stainless steel mesh band.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-NEUTRA", "Silver", 24),
#     },
#     {
#         "name": "Carlie Rose Gold Watch",
#         "category": "Watches", "brand": "Fossil",
#         "base_price": Decimal("10995.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A rose gold-tone women's watch with a crystal-accented dial.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-CARLIE", "Rose Gold", 20),
#     },
#     {
#         "name": "Townsman Leather Watch",
#         "category": "Watches", "brand": "Fossil",
#         "base_price": Decimal("11995.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A classic three-hand watch with a date window on a leather strap.",
#         "is_featured": False,
#         "variants": _onesize_variant("FOSSIL-TOWNSMAN", "Black", 18),
#     },
#     # --- Eyewear (5) ---
#     {
#         "name": "Aviator Classic Sunglasses",
#         "category": "Eyewear", "brand": "Ray-Ban",
#         "base_price": Decimal("8990.00"), "discount_percentage": Decimal("0.00"),
#         "description": "The original teardrop aviator with G-15 lenses and a gold frame.",
#         "is_featured": True,
#         "variants": _onesize_variant("RAYBAN-AVIATOR", "Gold", 26),
#     },
#     {
#         "name": "Wayfarer Sunglasses",
#         "category": "Eyewear", "brand": "Ray-Ban",
#         "base_price": Decimal("7990.00"), "discount_percentage": Decimal("0.00"),
#         "description": "The icon of casual cool — acetate frame with crystal green lenses.",
#         "is_featured": False,
#         "variants": _onesize_variant("RAYBAN-WAYFARER", "Black", 30),
#     },
#     {
#         "name": "Round Metal Sunglasses",
#         "category": "Eyewear", "brand": "Ray-Ban",
#         "base_price": Decimal("8490.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A thin round metal frame inspired by 1960s counterculture style.",
#         "is_featured": False,
#         "variants": _onesize_variant("RAYBAN-ROUND", "Gunmetal", 22),
#     },
#     {
#         "name": "Clubmaster Sunglasses",
#         "category": "Eyewear", "brand": "Ray-Ban",
#         "base_price": Decimal("9490.00"), "discount_percentage": Decimal("5.00"),
#         "description": "A browline acetate frame with a retro silhouette.",
#         "is_featured": False,
#         "variants": _onesize_variant("RAYBAN-CLUBMASTER", "Tortoise", 20),
#     },
#     {
#         "name": "Erika Sunglasses",
#         "category": "Eyewear", "brand": "Ray-Ban",
#         "base_price": Decimal("7490.00"), "discount_percentage": Decimal("0.00"),
#         "description": "An oversized round-square frame with a lightweight nylon lens.",
#         "is_featured": False,
#         "variants": _onesize_variant("RAYBAN-ERIKA", "Havana", 24),
#     },
#     # --- Sportswear (5) ---
#     {
#         "name": "HeatGear Compression Tee",
#         "category": "Sportswear", "brand": "Under Armour",
#         "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A second-skin compression tee that wicks sweat and regulates body temperature.",
#         "is_featured": False,
#         "variants": _apparel_variants("UA-HEATGEAR", ["S", "M", "L"], ["Black", "Navy"]),
#     },
#     {
#         "name": "Dri-FIT Running Shorts",
#         "category": "Sportswear", "brand": "Nike",
#         "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Lightweight running shorts with a built-in brief liner.",
#         "is_featured": False,
#         "variants": _apparel_variants("NIKE-RUNSHORT", ["S", "M", "L"], ["Black", "Grey"]),
#     },
#     {
#         "name": "Techfit Training Tights",
#         "category": "Sportswear", "brand": "Adidas",
#         "base_price": Decimal("2999.00"), "discount_percentage": Decimal("10.00"),
#         "description": "Compression-fit tights that move with you through any training session.",
#         "is_featured": True,
#         "variants": _apparel_variants("ADIDAS-TECHFIT", ["S", "M", "L"], ["Black"]),
#     },
#     {
#         "name": "Training Tank Top",
#         "category": "Sportswear", "brand": "Puma",
#         "base_price": Decimal("1399.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A breathable training tank with dryCELL sweat-wicking technology.",
#         "is_featured": False,
#         "variants": _apparel_variants("PUMA-TANK", ["S", "M", "L"], ["Red", "Black"]),
#     },
#     {
#         "name": "CrossFit Training Shorts",
#         "category": "Sportswear", "brand": "Reebok",
#         "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Durable training shorts built for high-intensity functional fitness.",
#         "is_featured": False,
#         "variants": _apparel_variants("REEBOK-CFSHORT", ["S", "M", "L"], ["Black"]),
#     },
#     # --- Ethnic Wear (5) ---
#     {
#         "name": "Embroidered Kurta Set",
#         "category": "Ethnic Wear", "brand": "Zara",
#         "base_price": Decimal("4499.00"), "discount_percentage": Decimal("15.00"),
#         "description": "A thread-embroidered kurta paired with a matching bottom.",
#         "is_featured": True,
#         "variants": _apparel_variants("ZARA-KURTASET", ["S", "M", "L"], ["Maroon", "Mustard"]),
#     },
#     {
#         "name": "Printed Anarkali Dress",
#         "category": "Ethnic Wear", "brand": "H&M",
#         "base_price": Decimal("3999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A flowing Anarkali silhouette in a floral block print.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-ANARKALI", ["S", "M", "L"], ["Teal", "Pink"]),
#     },
#     {
#         "name": "Linen Kurta",
#         "category": "Ethnic Wear", "brand": "Uniqlo",
#         "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A breathable linen kurta with a mandarin collar, built for warm weather.",
#         "is_featured": False,
#         "variants": _apparel_variants("UNIQLO-KURTA", ["M", "L", "XL"], ["White", "Beige"]),
#     },
#     {
#         "name": "Nehru Jacket",
#         "category": "Ethnic Wear", "brand": "Zara",
#         "base_price": Decimal("3499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A structured collarless jacket, layers over a kurta or shirt.",
#         "is_featured": False,
#         "variants": _apparel_variants("ZARA-NEHRU", ["M", "L"], ["Black", "Navy"]),
#     },
#     {
#         "name": "Bandhani Print Dupatta Set",
#         "category": "Ethnic Wear", "brand": "H&M",
#         "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A traditional bandhani-print dupatta with a coordinating kurta set.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-BANDHANI", ["S", "M", "L"], ["Pink", "Yellow"]),
#     },
#     # --- Winter Wear (5) ---
#     {
#         "name": "Ultra Light Down Puffer Jacket",
#         "category": "Winter Wear", "brand": "Uniqlo",
#         "base_price": Decimal("5990.00"), "discount_percentage": Decimal("10.00"),
#         "description": "A packable puffer jacket with 90% duck down fill, warm at a fraction of the weight.",
#         "is_featured": True,
#         "variants": _apparel_variants("UNIQLO-PUFFER", ["S", "M", "L", "XL"], ["Black", "Navy"]),
#     },
#     {
#         "name": "Wool Blend Overcoat",
#         "category": "Winter Wear", "brand": "H&M",
#         "base_price": Decimal("6999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A single-breasted overcoat in a wool blend, tailored for a clean silhouette.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-OVERCOAT", ["M", "L", "XL"], ["Camel", "Charcoal"]),
#     },
#     {
#         "name": "Cable Knit Sweater",
#         "category": "Winter Wear", "brand": "Zara",
#         "base_price": Decimal("2999.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A chunky cable-knit sweater in soft brushed yarn.",
#         "is_featured": False,
#         "variants": _apparel_variants("ZARA-CABLEKNIT", ["S", "M", "L"], ["Cream", "Grey"]),
#     },
#     {
#         "name": "Fleece Zip Hoodie",
#         "category": "Winter Wear", "brand": "Adidas",
#         "base_price": Decimal("3499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A full-zip fleece hoodie with a brushed interior for warmth.",
#         "is_featured": False,
#         "variants": _apparel_variants("ADIDAS-FLEECEHOOD", ["M", "L", "XL"], ["Black", "Grey"]),
#     },
#     {
#         "name": "Sherpa Trucker Jacket",
#         "category": "Winter Wear", "brand": "Levi's",
#         "base_price": Decimal("6499.00"), "discount_percentage": Decimal("5.00"),
#         "description": "The classic trucker jacket lined with cozy sherpa fleece.",
#         "is_featured": False,
#         "variants": _apparel_variants("LEVIS-SHERPA", ["M", "L", "XL"], ["Denim Blue"]),
#     },
#     # --- Innerwear & Loungewear (5) ---
#     {
#         "name": "Airism Boxer Briefs (3-Pack)",
#         "category": "Innerwear & Loungewear", "brand": "Uniqlo",
#         "base_price": Decimal("1490.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Breathable, quick-drying boxer briefs, sold as a pack of three.",
#         "is_featured": False,
#         "variants": _apparel_variants("UNIQLO-BOXER3", ["S", "M", "L"], ["Assorted"]),
#     },
#     {
#         "name": "Cotton Lounge Pants",
#         "category": "Innerwear & Loungewear", "brand": "H&M",
#         "base_price": Decimal("1299.00"), "discount_percentage": Decimal("0.00"),
#         "description": "Relaxed-fit lounge pants in soft brushed cotton with an elastic waistband.",
#         "is_featured": False,
#         "variants": _apparel_variants("HM-LOUNGEPANT", ["S", "M", "L"], ["Grey", "Navy"]),
#     },
#     {
#         "name": "Ribbed Cami & Shorts Set",
#         "category": "Innerwear & Loungewear", "brand": "Zara",
#         "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A ribbed cami top and matching shorts, made for easy at-home wear.",
#         "is_featured": False,
#         "variants": _apparel_variants("ZARA-CAMISET", ["XS", "S", "M"], ["Sage", "Blush"]),
#     },
#     {
#         "name": "Seamless Sports Bra",
#         "category": "Innerwear & Loungewear", "brand": "Puma",
#         "base_price": Decimal("1499.00"), "discount_percentage": Decimal("0.00"),
#         "description": "A medium-support seamless sports bra with moisture-wicking fabric.",
#         "is_featured": False,
#         "variants": _apparel_variants("PUMA-SPORTSBRA", ["S", "M", "L"], ["Black", "Grey"]),
#     },
#     {
#         "name": "Boxerjock Briefs (2-Pack)",
#         "category": "Innerwear & Loungewear", "brand": "Under Armour",
#         "base_price": Decimal("1599.00"), "discount_percentage": Decimal("0.00"),
#         "description": "6-inch inseam boxerjock briefs with an anti-odor finish, pack of two.",
#         "is_featured": False,
#         "variants": _apparel_variants("UA-BOXERJOCK2", ["S", "M", "L"], ["Black"]),
#     },
# ]


# def seed_products(db, categories: dict[str, Category], brands: dict[str, Brand]) -> None:
#     for spec in PRODUCTS:
#         slug = slugify(spec["name"])
#         existing = db.query(Product).filter(Product.slug == slug).first()
#         if existing:
#             print(f"  [skip] product '{spec['name']}' already exists")
#             continue

#         product = Product(
#             name=spec["name"],
#             slug=slug,
#             description=spec["description"],
#             category_id=categories[spec["category"]].id,
#             brand_id=brands[spec["brand"]].id,
#             base_price=spec["base_price"],
#             discount_percentage=spec["discount_percentage"],
#             gst_percentage=Decimal("12.00"),
#             # ACTIVE, not the model's default DRAFT — GET /api/v1/products
#             # filters on status == ACTIVE (see api/v1/catalog.py), so
#             # seeding as DRAFT would insert rows that still never appear
#             # on the storefront. This is the exact "empty database" bug
#             # from audit item #3, just moved one layer deeper.
#             status=ProductStatus.ACTIVE,
#             is_featured=spec["is_featured"],
#             is_trending=False,
#         )
#         product.variants = [
#             ProductVariant(
#                 sku=v["sku"],
#                 size=v["size"],
#                 color=v["color"],
#                 stock_quantity=v["stock_quantity"],
#             )
#             for v in spec["variants"]
#         ]
#         db.add(product)
#         db.commit()
#         db.refresh(product)

#         # Two images per product: one primary, one secondary — enough for
#         # ProductOut.primary_image_url (list/grid view) and the detail
#         # page's image gallery to both have real data to render.
#         db.add(
#             ProductImage(
#                 product_id=product.id,
#                 image_url=_placeholder_image_url(f"{slug}-1"),
#                 is_primary=True,
#                 display_order=0,
#             )
#         )
#         db.add(
#             ProductImage(
#                 product_id=product.id,
#                 image_url=_placeholder_image_url(f"{slug}-2"),
#                 is_primary=False,
#                 display_order=1,
#             )
#         )
#         db.commit()
#         print(f"  [ok] created product: {spec['name']} ({len(spec['variants'])} variant(s), 2 image(s))")


# def seed_coupons(db) -> None:
#     """Optional, per audit item #3's brief — a couple of realistic coupons
#     so the cart/checkout flow has something to actually apply."""
#     coupons = [
#         {
#             "code": "WELCOME10",
#             "discount_type": DiscountType.PERCENTAGE,
#             "discount_value": Decimal("10.00"),
#             "max_discount_amount": Decimal("500.00"),
#             "min_order_value": Decimal("999.00"),
#         },
#         {
#             "code": "FLAT200",
#             "discount_type": DiscountType.FLAT,
#             "discount_value": Decimal("200.00"),
#             "max_discount_amount": None,
#             "min_order_value": Decimal("1999.00"),
#         },
#     ]
#     for spec in coupons:
#         existing = db.query(Coupon).filter(Coupon.code == spec["code"]).first()
#         if existing:
#             print(f"  [skip] coupon '{spec['code']}' already exists")
#             continue
#         db.add(Coupon(**spec, usage_limit=None, times_used=0, is_active=True))
#         db.commit()
#         print(f"  [ok] created coupon: {spec['code']}")


# def main() -> None:
#     # Fail fast and clearly if the database isn't reachable at all — the
#     # same "clear error over a buried traceback" philosophy already used
#     # in app/core/config.py._load_settings().
#     try:
#         with engine.connect():
#             pass
#     except Exception as exc:  # noqa: BLE001 - intentionally broad, this is a CLI entrypoint
#         print(
#             "\n=== Could not connect to the database ===\n"
#             f"{exc}\n\n"
#             "Check that DATABASE_URL in backend/.env points at a running "
#             "Postgres instance, and that `alembic upgrade head` has already "
#             "been run.\n",
#             file=sys.stderr,
#         )
#         raise SystemExit(1) from exc

#     # Verify migrations have actually been applied — a missing 'users'
#     # table means alembic upgrade head hasn't run yet, and every insert
#     # below would otherwise fail with a confusing "relation does not
#     # exist" instead of a clear instruction.
#     # NOTE: Table.exists(bind=...) was removed in SQLAlchemy 2.0 (this
#     # project pins sqlalchemy==2.0.35) — inspect(engine).has_table(...) is
#     # the current, correct replacement.
#     if not inspect(engine).has_table("users"):
#         print(
#             "\n=== Tables not found ===\n"
#             "Run `alembic upgrade head` before `python seed.py` — the "
#             "'users' table doesn't exist yet, so migrations haven't been "
#             "applied.\n",
#             file=sys.stderr,
#         )
#         raise SystemExit(1)

#     db = SessionLocal()
#     try:
#         print("Seeding admin user...")
#         seed_admin(db)

#         print("Seeding categories...")
#         categories = seed_categories(db)

#         print("Seeding brands...")
#         brands = seed_brands(db)

#         print("Seeding products, variants, and images...")
#         seed_products(db, categories, brands)

#         print("Seeding coupons...")
#         seed_coupons(db)

#         print("\nDone. Fresh install now has data — restart is not required, it's already live.")
#         print(f"Admin login -> email: {settings.DEFAULT_ADMIN_EMAIL}  password: {settings.DEFAULT_ADMIN_PASSWORD}")
#     finally:
#         db.close()


# if __name__ == "__main__":
#     main()



"""
Database seed script — audit items #3 ("Empty Database"), #4 ("Product
Images"), and #12 ("Seed Script").

WHY THIS FILE EXISTS AT ALL:
Before this fix, a fresh `alembic upgrade head` created a schema with zero
rows in it. That meant: no admin user (so every admin endpoint 403'd —
there was nothing WITH the admin role to log in as), no categories/brands
(so the admin UI's "create product" dropdowns were empty), and no
products/images (so the storefront home page always showed "No products
yet." and GET /api/v1/products always returned {"items": [], "total": 0}
on a brand new install). The project's own setup instructions
(README "Getting Started") never mentioned any manual SQL step — so a new
developer following them exactly would land on a broken-looking app
through no fault of their own. This script is the actual fix: it is the
"proper database seeding system" the audit brief asked for, not a
suggestion to write one.

WHY A PLAIN SCRIPT, NOT AN ALEMBIC DATA MIGRATION:
Schema changes (tables/columns) belong in Alembic migrations because every
environment must apply them exactly once, in order, forever. Seed DATA is
different — it's "give me something to develop against," which you often
want to re-run, skip in CI, or run against a copy of prod for a demo
environment. Baking sample products into a schema migration would mean
"alembic upgrade head" inserts fake products into a REAL production
database the first time someone runs it there. A standalone script that
an engineer explicitly runs (`python seed.py`) keeps that decision in
human hands.

WHY THIS IS SAFE TO RUN MULTIPLE TIMES (idempotency):
Every insert below is preceded by an existence check on that row's real
unique key (email for the admin user, slug for categories/brands/products,
sku for variants, code for coupons) — see `_get_or_create` and the
per-entity checks. Running `python seed.py` a second time against a
database that already has this data prints "already exists, skipping"
for everything and creates nothing new or duplicated. This matters
because the setup instructions tell every new developer to run this
script as a normal setup step — it has to be safe if someone runs it
twice by mistake, or re-runs it after pulling a teammate's migration.

USAGE:
    cd backend
    python seed.py
"""
from __future__ import annotations

import hashlib
import sys
import textwrap
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import inspect

from app.core.security import hash_password
from app.db.session import SessionLocal, engine

# Import every model module so Base.metadata is fully populated before we
# touch the database — mirrors alembic/env.py's import list exactly, for
# the same reason (SQLAlchemy needs every mapped class registered before
# relationships between them can be resolved).
from app.models.address import Address  # noqa: F401
from app.models.cart import Cart, CartItem  # noqa: F401
from app.models.catalog import Brand, Category, Product, ProductImage, ProductStatus, ProductVariant
from app.models.coupon import Coupon, DiscountType
from app.models.delivery import DeliveryPartner, TrackingEvent  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.order import Order, OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.review import Review  # noqa: F401
from app.models.search_log import SearchQuery  # noqa: F401
from app.models.user import User, UserRole
from app.schemas.catalog import slugify
from app.core.config import settings


def seed_admin(db) -> None:
    """Audit item #2: fresh installs had no ADMIN user at all, so every
    admin-only endpoint correctly returned 403 — there was no bug in the
    403 itself, just nobody who was actually allowed in. Existence check
    is by email (the column the login flow itself keys off of).

    Seeded as SUPER_ADMIN, not ADMIN: app/api/v1/admin_users.py gates its
    /role endpoint behind `require_role(UserRole.SUPER_ADMIN)` specifically
    (by design — see that file's docstring on why role changes are
    restricted beyond plain ADMIN). A bootstrap account seeded as ADMIN
    would still 403 on that one route with nobody able to grant SUPER_ADMIN
    to anyone, ever, without a manual DB edit — exactly the kind of
    "never touch SQL by hand" violation this whole audit is trying to
    eliminate. One SUPER_ADMIN seed account can create/promote further
    ADMIN accounts through the API itself from here on."""
    existing = db.query(User).filter(User.email == settings.DEFAULT_ADMIN_EMAIL.lower()).first()
    if existing:
        print(f"  [skip] admin user '{settings.DEFAULT_ADMIN_EMAIL}' already exists")
        return

    admin = User(
        full_name=settings.DEFAULT_ADMIN_FULL_NAME,
        email=settings.DEFAULT_ADMIN_EMAIL.lower(),
        hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_email_verified=True,
    )
    db.add(admin)
    db.commit()
    print(f"  [ok] created admin user: {settings.DEFAULT_ADMIN_EMAIL} / {settings.DEFAULT_ADMIN_PASSWORD}")


CATEGORY_NAMES = [
    "Men",
    "Women",
    "Kids",
    "Footwear",
    "Accessories",
    "Bags",
    "Watches",
    "Eyewear",
    "Sportswear",
    "Ethnic Wear",
    "Winter Wear",
    "Innerwear & Loungewear",
]


def seed_categories(db) -> dict[str, Category]:
    names = CATEGORY_NAMES
    result: dict[str, Category] = {}
    for name in names:
        slug = slugify(name)
        existing = db.query(Category).filter(Category.slug == slug).first()
        if existing:
            print(f"  [skip] category '{name}' already exists")
            result[name] = existing
            continue
        category = Category(name=name, slug=slug)
        db.add(category)
        db.commit()
        db.refresh(category)
        result[name] = category
        print(f"  [ok] created category: {name}")
    return result


BRAND_NAMES = [
    "Nike",
    "Adidas",
    "Puma",
    "Levi's",
    "Zara",
    "H&M",
    "Under Armour",
    "Reebok",
    "Fossil",
    "Ray-Ban",
    "Uniqlo",
    "Woodland",
]


def seed_brands(db) -> dict[str, Brand]:
    names = BRAND_NAMES
    result: dict[str, Brand] = {}
    for name in names:
        slug = slugify(name)
        existing = db.query(Brand).filter(Brand.slug == slug).first()
        if existing:
            print(f"  [skip] brand '{name}' already exists")
            result[name] = existing
            continue
        brand = Brand(name=name, slug=slug)
        db.add(brand)
        db.commit()
        db.refresh(brand)
        result[name] = brand
        print(f"  [ok] created brand: {name}")
    return result


# --- Placeholder product photography ---
#
# THIS REPLACES AN EARLIER VERSION THAT CALLED picsum.photos/seed/{slug}.
# picsum returns arbitrary stock photography — a random photo of a
# building, a dog, a landscape, whatever happens to hash to that seed
# string. It IS deterministic (same seed -> same photo on every re-run),
# but "deterministic" and "matches the product" are different things:
# picsum has no idea "511 Slim Fit Jeans" is a pair of jeans, so it just
# as easily hands back a picture of a mountain. That mismatch between
# product title and product photo was exactly the bug report — the fix
# has to be "the image reflects what the product actually is," not just
# "the image doesn't change on re-run."
#
# So instead of fetching a photo from anywhere, we RENDER one: a clean
# card carrying the product's own name, brand, and category, drawn with
# Pillow onto a color that's derived from the category (so every product
# in "Footwear" shares a family color, etc.). This guarantees, by
# construction, that a product's image always matches its title — there
# is no external source of truth to drift out of sync with. It also
# writes through save_product_image()'s own storage convention
# (media/products/{product_id}/{file}.jpg -> "/media/products/..." URL),
# the exact same relative-URL shape a real admin image upload produces,
# so getMediaUrl() on the frontend (see frontend/lib/media.ts) handles it
# identically either way.
MEDIA_ROOT = Path(__file__).resolve().parent / "media"

_CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "Men": (37, 63, 108),
    "Women": (142, 45, 84),
    "Footwear": (58, 90, 64),
    "Accessories": (120, 72, 26),
    "Bags": (101, 63, 33),
    "Ethnic Wear": (150, 63, 22),
    "Eyewear": (35, 78, 92),
    "Innerwear & Loungewear": (110, 88, 130),
    "Kids": (176, 120, 30),
    "Sportswear": (32, 96, 84),
    "Watches": (66, 58, 40),
    "Winter Wear": (48, 72, 96),
    "Electronics": (45, 45, 58),
    "Home": (94, 74, 42),
}
_DEFAULT_COLOR = (55, 55, 65)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Try a couple of common Linux/Docker font paths; DejaVu Sans ships
    # with most base Python/Debian images. Fall back to Pillow's built-in
    # bitmap font (uglier, but never crashes the seed run over a missing
    # font file).
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _generate_placeholder_image(
    product_id, slug: str, name: str, brand: str, category: str, suffix: str
) -> str:
    # Same product + same suffix ("-1"/"-2") always renders identically —
    # keeps re-running the seed script idempotent-looking even though the
    # actual bytes are regenerated each time.
    shade_seed = int(hashlib.sha256(f"{slug}{suffix}".encode()).hexdigest(), 16)
    base_color = _CATEGORY_COLORS.get(category, _DEFAULT_COLOR)
    # Slightly vary lightness between a product's two images so they're
    # visibly distinct in the gallery, not identical twins.
    offset = (shade_seed % 25) - 12
    color = tuple(max(0, min(255, c + offset)) for c in base_color)

    width, height = 900, 1125
    image = Image.new("RGB", (width, height), color=color)
    draw = ImageDraw.Draw(image)

    # A darker footer band anchors the brand/category text and keeps it
    # legible regardless of the random-ish background shade.
    band_height = 220
    band_color = tuple(max(0, c - 35) for c in color)
    draw.rectangle([(0, height - band_height), (width, height)], fill=band_color)

    name_font = _load_font(56)
    meta_font = _load_font(32)
    wrapped_name = textwrap.wrap(name, width=18)[:4]

    text_y = height - band_height - (len(wrapped_name) * 68) - 40
    for line in wrapped_name:
        bbox = draw.textbbox((0, 0), line, font=name_font)
        line_width = bbox[2] - bbox[0]
        draw.text(((width - line_width) / 2, text_y), line, font=name_font, fill=(255, 255, 255))
        text_y += 68

    meta_text = f"{brand} · {category}"
    bbox = draw.textbbox((0, 0), meta_text, font=meta_font)
    meta_width = bbox[2] - bbox[0]
    draw.text(
        ((width - meta_width) / 2, height - band_height / 2 - 16),
        meta_text,
        font=meta_font,
        fill=(230, 230, 230),
    )

    product_dir = MEDIA_ROOT / "products" / str(product_id)
    product_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slug}{suffix}.jpg"
    image.save(product_dir / filename, format="JPEG", quality=88, optimize=True)

    return f"/media/products/{product_id}/{filename}"


# WHY HELPER FUNCTIONS BUILD THE VARIANT LISTS BELOW, INSTEAD OF WRITING
# EACH VARIANT DICT BY HAND (like the previous 8-product version did):
# at 60 products, hand-writing every {"sku": ..., "size": ..., "color": ...,
# "stock_quantity": ...} risks exactly the kind of copy-paste typo that
# causes a duplicate SKU across two unrelated products — which would
# violate ProductVariant's real uq_variant_sku constraint (see
# app/models/catalog.py) and crash the whole seed run on insert. These
# three helpers guarantee a unique, deterministic SKU per (product, size,
# color) combination from the product's own SKU prefix, so uniqueness is
# structural instead of "please don't typo it."
def _apparel_variants(prefix: str, sizes: list[str], colors: list[str], base_stock: int = 20) -> list[dict]:
    variants = []
    for i, size in enumerate(sizes):
        color = colors[i % len(colors)]
        variants.append(
            {
                "sku": f"{prefix}-{size}-{color[:3].upper()}",
                "size": size,
                "color": color,
                "stock_quantity": base_stock + (i * 5),
            }
        )
    return variants


def _shoe_variants(prefix: str, sizes: list[str], colors: list[str], base_stock: int = 15) -> list[dict]:
    variants = []
    for i, size in enumerate(sizes):
        color = colors[i % len(colors)]
        variants.append(
            {
                "sku": f"{prefix}-{size}-{color[:3].upper()}",
                "size": size,
                "color": color,
                "stock_quantity": base_stock + (i * 4),
            }
        )
    return variants


def _onesize_variant(prefix: str, color: str, stock: int = 40) -> list[dict]:
    return [{"sku": f"{prefix}-ONE-{color[:3].upper()}", "size": None, "color": color, "stock_quantity": stock}]


PRODUCTS: list[dict] = [
    # --- Men (5) ---
    {
        "name": "511 Slim Fit Jeans",
        "category": "Men", "brand": "Levi's",
        "base_price": Decimal("3999.00"), "discount_percentage": Decimal("10.00"),
        "description": "A slim fit through the seat and thigh with a tapered leg, cut from stretch denim.",
        "is_featured": True,
        "variants": _apparel_variants("LEVIS-511", ["30", "32", "34"], ["Indigo", "Black"]),
    },
    {
        "name": "Regular Fit Oxford Shirt",
        "category": "Men", "brand": "Zara",
        "base_price": Decimal("2999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A crisp cotton Oxford shirt with a button-down collar, cut for a regular fit.",
        "is_featured": False,
        "variants": _apparel_variants("ZARA-OXFORD", ["S", "M", "L"], ["White", "Sky Blue"]),
    },
    {
        "name": "Slim Fit Chino Trousers",
        "category": "Men", "brand": "H&M",
        "base_price": Decimal("2499.00"), "discount_percentage": Decimal("5.00"),
        "description": "Stretch cotton chinos with a slim leg and a comfortable mid-rise waist.",
        "is_featured": False,
        "variants": _apparel_variants("HM-CHINO", ["30", "32", "34"], ["Khaki", "Navy"]),
    },
    {
        "name": "Airism Crew Neck Tee",
        "category": "Men", "brand": "Uniqlo",
        "base_price": Decimal("990.00"), "discount_percentage": Decimal("0.00"),
        "description": "A moisture-wicking, quick-drying crew neck tee for everyday wear.",
        "is_featured": True,
        "variants": _apparel_variants("UNIQLO-AIRISM-M", ["S", "M", "L", "XL"], ["Grey", "Black"]),
    },
    {
        "name": "Dri-FIT Training Tee",
        "category": "Men", "brand": "Nike",
        "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
        "description": "Sweat-wicking training tee with a relaxed fit and dropped hem.",
        "is_featured": False,
        "variants": _apparel_variants("NIKE-DRIFIT-M", ["M", "L", "XL"], ["Black", "Grey"]),
    },
    # --- Women (5) ---
    {
        "name": "Satin Wrap Midi Dress",
        "category": "Women", "brand": "Zara",
        "base_price": Decimal("3299.00"), "discount_percentage": Decimal("20.00"),
        "description": "A wrap-front midi dress in fluid satin, finished with a self-tie belt.",
        "is_featured": True,
        "variants": _apparel_variants("ZARA-WRAP", ["S", "M", "L"], ["Black", "Wine"]),
    },
    {
        "name": "Ribbed Knit Bodysuit",
        "category": "Women", "brand": "H&M",
        "base_price": Decimal("1299.00"), "discount_percentage": Decimal("0.00"),
        "description": "A fitted ribbed bodysuit with a scoop neck, layers cleanly under blazers.",
        "is_featured": False,
        "variants": _apparel_variants("HM-BODYSUIT", ["XS", "S", "M"], ["Black", "Ecru"]),
    },
    {
        "name": "Ultra Light Down Vest",
        "category": "Women", "brand": "Uniqlo",
        "base_price": Decimal("3990.00"), "discount_percentage": Decimal("10.00"),
        "description": "A packable down vest with a DWR finish, warm without the bulk.",
        "is_featured": False,
        "variants": _apparel_variants("UNIQLO-DOWNVEST-W", ["S", "M", "L"], ["Navy", "Beige"]),
    },
    {
        "name": "501 High Rise Jeans",
        "category": "Women", "brand": "Levi's",
        "base_price": Decimal("4299.00"), "discount_percentage": Decimal("0.00"),
        "description": "The original straight fit, reworked with a high rise for a longer leg line.",
        "is_featured": False,
        "variants": _apparel_variants("LEVIS-501-W", ["26", "28", "30"], ["Light Blue", "Black"]),
    },
    {
        "name": "Tailored Single-Breasted Blazer",
        "category": "Women", "brand": "Zara",
        "base_price": Decimal("5999.00"), "discount_percentage": Decimal("15.00"),
        "description": "A structured blazer with a tailored waist, works over both tees and shirts.",
        "is_featured": True,
        "variants": _apparel_variants("ZARA-BLAZER-W", ["S", "M", "L"], ["Black", "Camel"]),
    },
    # --- Kids (5) ---
    {
        "name": "Cotton Graphic Print Tee",
        "category": "Kids", "brand": "H&M",
        "base_price": Decimal("799.00"), "discount_percentage": Decimal("0.00"),
        "description": "100% cotton crew-neck tee with a front graphic print, pre-shrunk fabric.",
        "is_featured": False,
        "variants": _apparel_variants("HM-KIDTEE", ["4Y", "6Y", "8Y"], ["Red", "Blue"]),
    },
    {
        "name": "Fleece Zip-Up Hoodie",
        "category": "Kids", "brand": "Uniqlo",
        "base_price": Decimal("1490.00"), "discount_percentage": Decimal("0.00"),
        "description": "Soft fleece hoodie with a full front zip, sized for layering.",
        "is_featured": False,
        "variants": _apparel_variants("UNIQLO-KIDHOOD", ["6Y", "8Y", "10Y"], ["Grey", "Navy"]),
    },
    {
        "name": "Junior Track Suit Set",
        "category": "Kids", "brand": "Adidas",
        "base_price": Decimal("2999.00"), "discount_percentage": Decimal("10.00"),
        "description": "A matching zip jacket and jogger set in soft-touch fleece.",
        "is_featured": True,
        "variants": _apparel_variants("ADIDAS-KIDTRACK", ["6Y", "8Y", "10Y"], ["Navy", "Black"]),
    },
    {
        "name": "Denim Dungaree Overalls",
        "category": "Kids", "brand": "H&M",
        "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
        "description": "Adjustable-strap denim overalls with front pocket detail.",
        "is_featured": False,
        "variants": _apparel_variants("HM-DUNGAREE", ["4Y", "6Y"], ["Blue"]),
    },
    {
        "name": "Junior Running Shoes",
        "category": "Kids", "brand": "Puma",
        "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
        "description": "Lightweight running shoes with a hook-and-loop strap for easy wear.",
        "is_featured": False,
        "variants": _shoe_variants("PUMA-KIDRUN", ["UK1", "UK2", "UK3"], ["Black", "Red"]),
    },
    # --- Footwear (5) ---
    {
        "name": "Air Runner Sneakers",
        "category": "Footwear", "brand": "Nike",
        "base_price": Decimal("6999.00"), "discount_percentage": Decimal("10.00"),
        "description": "Lightweight everyday running sneakers with breathable mesh uppers.",
        "is_featured": True,
        "variants": _shoe_variants("NIKE-AIRRUN", ["UK7", "UK8", "UK9", "UK10"], ["Black", "White"]),
    },
    {
        "name": "Ultraboost Running Shoes",
        "category": "Footwear", "brand": "Adidas",
        "base_price": Decimal("13999.00"), "discount_percentage": Decimal("15.00"),
        "description": "Responsive Boost midsole with a Primeknit upper for all-day comfort.",
        "is_featured": True,
        "variants": _shoe_variants("ADIDAS-ULTRABOOST", ["UK7", "UK8", "UK9"], ["Black", "Grey"]),
    },
    {
        "name": "Cloud Cushion Slides",
        "category": "Footwear", "brand": "Puma",
        "base_price": Decimal("1999.00"), "discount_percentage": Decimal("15.00"),
        "description": "Everyday cushioned slides for post-workout comfort.",
        "is_featured": False,
        "variants": _shoe_variants("PUMA-SLIDE", ["UK7", "UK8", "UK9"], ["Grey", "Black"]),
    },
    {
        "name": "Classic Leather Sneakers",
        "category": "Footwear", "brand": "Reebok",
        "base_price": Decimal("4499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A timeless low-top leather sneaker with a cupsole and suede accents.",
        "is_featured": False,
        "variants": _shoe_variants("REEBOK-CLASSIC", ["UK7", "UK8", "UK9", "UK10"], ["White", "Grey"]),
    },
    {
        "name": "Trek Leather Boots",
        "category": "Footwear", "brand": "Woodland",
        "base_price": Decimal("5499.00"), "discount_percentage": Decimal("5.00"),
        "description": "Rugged full-grain leather boots with a grippy lug outsole for the outdoors.",
        "is_featured": False,
        "variants": _shoe_variants("WOODLAND-TREK", ["UK8", "UK9", "UK10"], ["Brown", "Tan"]),
    },
    # --- Accessories (5) ---
    {
        "name": "Bifold Leather Wallet",
        "category": "Accessories", "brand": "Fossil",
        "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A slim bifold wallet in full-grain leather with six card slots.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-WALLET", "Brown", 30) + _onesize_variant("FOSSIL-WALLET", "Black", 30),
    },
    {
        "name": "Reversible Leather Belt",
        "category": "Accessories", "brand": "Zara",
        "base_price": Decimal("1499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A reversible belt with a rotating buckle, switches from black to brown.",
        "is_featured": False,
        "variants": _apparel_variants("ZARA-BELT", ["M", "L"], ["Black/Brown"]),
    },
    {
        "name": "Ribbed Wool Beanie",
        "category": "Accessories", "brand": "H&M",
        "base_price": Decimal("699.00"), "discount_percentage": Decimal("0.00"),
        "description": "A snug ribbed-knit beanie in a soft wool blend.",
        "is_featured": False,
        "variants": _onesize_variant("HM-BEANIE", "Charcoal", 50),
    },
    {
        "name": "Curb Chain Bracelet",
        "category": "Accessories", "brand": "Fossil",
        "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A stainless steel curb-chain bracelet with a lobster clasp.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-BRACELET", "Silver", 25),
    },
    {
        "name": "Printed Silk Scarf",
        "category": "Accessories", "brand": "Zara",
        "base_price": Decimal("1299.00"), "discount_percentage": Decimal("0.00"),
        "description": "A lightweight printed scarf in silk-blend fabric.",
        "is_featured": False,
        "variants": _onesize_variant("ZARA-SCARF", "Multicolor", 35),
    },
    # --- Bags (5) ---
    {
        "name": "Everyday Structured Tote Bag",
        "category": "Bags", "brand": "Zara",
        "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A structured tote in vegan leather, sized for a 13-inch laptop.",
        "is_featured": False,
        "variants": _onesize_variant("ZARA-TOTE", "Tan", 50),
    },
    {
        "name": "Canvas Travel Backpack",
        "category": "Bags", "brand": "Woodland",
        "base_price": Decimal("3499.00"), "discount_percentage": Decimal("10.00"),
        "description": "A durable canvas backpack with a padded laptop sleeve and leather trims.",
        "is_featured": True,
        "variants": _onesize_variant("WOODLAND-BACKPACK", "Olive", 22) + _onesize_variant("WOODLAND-BACKPACK", "Black", 22),
    },
    {
        "name": "Quilted Crossbody Bag",
        "category": "Bags", "brand": "H&M",
        "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
        "description": "A compact quilted crossbody with an adjustable chain strap.",
        "is_featured": False,
        "variants": _onesize_variant("HM-CROSSBODY", "Black", 40),
    },
    {
        "name": "Leather Messenger Bag",
        "category": "Bags", "brand": "Fossil",
        "base_price": Decimal("4999.00"), "discount_percentage": Decimal("5.00"),
        "description": "A full-grain leather messenger bag with a padded 15-inch laptop compartment.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-MESSENGER", "Cognac", 15),
    },
    {
        "name": "Mini Shoulder Bag",
        "category": "Bags", "brand": "Zara",
        "base_price": Decimal("2199.00"), "discount_percentage": Decimal("0.00"),
        "description": "A compact shoulder bag with a detachable chain strap.",
        "is_featured": False,
        "variants": _onesize_variant("ZARA-MINIBAG", "Black", 28),
    },
    # --- Watches (5) ---
    {
        "name": "Gen 6 Smartwatch",
        "category": "Watches", "brand": "Fossil",
        "base_price": Decimal("22995.00"), "discount_percentage": Decimal("10.00"),
        "description": "A Wear OS smartwatch with heart-rate tracking and a silicone strap.",
        "is_featured": True,
        "variants": _onesize_variant("FOSSIL-GEN6", "Black", 18),
    },
    {
        "name": "Grant Chronograph Watch",
        "category": "Watches", "brand": "Fossil",
        "base_price": Decimal("12995.00"), "discount_percentage": Decimal("0.00"),
        "description": "A chronograph dial watch on a genuine leather strap.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-GRANT", "Brown", 20),
    },
    {
        "name": "Neutra Minimalist Watch",
        "category": "Watches", "brand": "Fossil",
        "base_price": Decimal("9995.00"), "discount_percentage": Decimal("0.00"),
        "description": "A slim-case minimalist watch with a stainless steel mesh band.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-NEUTRA", "Silver", 24),
    },
    {
        "name": "Carlie Rose Gold Watch",
        "category": "Watches", "brand": "Fossil",
        "base_price": Decimal("10995.00"), "discount_percentage": Decimal("0.00"),
        "description": "A rose gold-tone women's watch with a crystal-accented dial.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-CARLIE", "Rose Gold", 20),
    },
    {
        "name": "Townsman Leather Watch",
        "category": "Watches", "brand": "Fossil",
        "base_price": Decimal("11995.00"), "discount_percentage": Decimal("0.00"),
        "description": "A classic three-hand watch with a date window on a leather strap.",
        "is_featured": False,
        "variants": _onesize_variant("FOSSIL-TOWNSMAN", "Black", 18),
    },
    # --- Eyewear (5) ---
    {
        "name": "Aviator Classic Sunglasses",
        "category": "Eyewear", "brand": "Ray-Ban",
        "base_price": Decimal("8990.00"), "discount_percentage": Decimal("0.00"),
        "description": "The original teardrop aviator with G-15 lenses and a gold frame.",
        "is_featured": True,
        "variants": _onesize_variant("RAYBAN-AVIATOR", "Gold", 26),
    },
    {
        "name": "Wayfarer Sunglasses",
        "category": "Eyewear", "brand": "Ray-Ban",
        "base_price": Decimal("7990.00"), "discount_percentage": Decimal("0.00"),
        "description": "The icon of casual cool — acetate frame with crystal green lenses.",
        "is_featured": False,
        "variants": _onesize_variant("RAYBAN-WAYFARER", "Black", 30),
    },
    {
        "name": "Round Metal Sunglasses",
        "category": "Eyewear", "brand": "Ray-Ban",
        "base_price": Decimal("8490.00"), "discount_percentage": Decimal("0.00"),
        "description": "A thin round metal frame inspired by 1960s counterculture style.",
        "is_featured": False,
        "variants": _onesize_variant("RAYBAN-ROUND", "Gunmetal", 22),
    },
    {
        "name": "Clubmaster Sunglasses",
        "category": "Eyewear", "brand": "Ray-Ban",
        "base_price": Decimal("9490.00"), "discount_percentage": Decimal("5.00"),
        "description": "A browline acetate frame with a retro silhouette.",
        "is_featured": False,
        "variants": _onesize_variant("RAYBAN-CLUBMASTER", "Tortoise", 20),
    },
    {
        "name": "Erika Sunglasses",
        "category": "Eyewear", "brand": "Ray-Ban",
        "base_price": Decimal("7490.00"), "discount_percentage": Decimal("0.00"),
        "description": "An oversized round-square frame with a lightweight nylon lens.",
        "is_featured": False,
        "variants": _onesize_variant("RAYBAN-ERIKA", "Havana", 24),
    },
    # --- Sportswear (5) ---
    {
        "name": "HeatGear Compression Tee",
        "category": "Sportswear", "brand": "Under Armour",
        "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A second-skin compression tee that wicks sweat and regulates body temperature.",
        "is_featured": False,
        "variants": _apparel_variants("UA-HEATGEAR", ["S", "M", "L"], ["Black", "Navy"]),
    },
    {
        "name": "Dri-FIT Running Shorts",
        "category": "Sportswear", "brand": "Nike",
        "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
        "description": "Lightweight running shorts with a built-in brief liner.",
        "is_featured": False,
        "variants": _apparel_variants("NIKE-RUNSHORT", ["S", "M", "L"], ["Black", "Grey"]),
    },
    {
        "name": "Techfit Training Tights",
        "category": "Sportswear", "brand": "Adidas",
        "base_price": Decimal("2999.00"), "discount_percentage": Decimal("10.00"),
        "description": "Compression-fit tights that move with you through any training session.",
        "is_featured": True,
        "variants": _apparel_variants("ADIDAS-TECHFIT", ["S", "M", "L"], ["Black"]),
    },
    {
        "name": "Training Tank Top",
        "category": "Sportswear", "brand": "Puma",
        "base_price": Decimal("1399.00"), "discount_percentage": Decimal("0.00"),
        "description": "A breathable training tank with dryCELL sweat-wicking technology.",
        "is_featured": False,
        "variants": _apparel_variants("PUMA-TANK", ["S", "M", "L"], ["Red", "Black"]),
    },
    {
        "name": "CrossFit Training Shorts",
        "category": "Sportswear", "brand": "Reebok",
        "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
        "description": "Durable training shorts built for high-intensity functional fitness.",
        "is_featured": False,
        "variants": _apparel_variants("REEBOK-CFSHORT", ["S", "M", "L"], ["Black"]),
    },
    # --- Ethnic Wear (5) ---
    {
        "name": "Embroidered Kurta Set",
        "category": "Ethnic Wear", "brand": "Zara",
        "base_price": Decimal("4499.00"), "discount_percentage": Decimal("15.00"),
        "description": "A thread-embroidered kurta paired with a matching bottom.",
        "is_featured": True,
        "variants": _apparel_variants("ZARA-KURTASET", ["S", "M", "L"], ["Maroon", "Mustard"]),
    },
    {
        "name": "Printed Anarkali Dress",
        "category": "Ethnic Wear", "brand": "H&M",
        "base_price": Decimal("3999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A flowing Anarkali silhouette in a floral block print.",
        "is_featured": False,
        "variants": _apparel_variants("HM-ANARKALI", ["S", "M", "L"], ["Teal", "Pink"]),
    },
    {
        "name": "Linen Kurta",
        "category": "Ethnic Wear", "brand": "Uniqlo",
        "base_price": Decimal("2499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A breathable linen kurta with a mandarin collar, built for warm weather.",
        "is_featured": False,
        "variants": _apparel_variants("UNIQLO-KURTA", ["M", "L", "XL"], ["White", "Beige"]),
    },
    {
        "name": "Nehru Jacket",
        "category": "Ethnic Wear", "brand": "Zara",
        "base_price": Decimal("3499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A structured collarless jacket, layers over a kurta or shirt.",
        "is_featured": False,
        "variants": _apparel_variants("ZARA-NEHRU", ["M", "L"], ["Black", "Navy"]),
    },
    {
        "name": "Bandhani Print Dupatta Set",
        "category": "Ethnic Wear", "brand": "H&M",
        "base_price": Decimal("1999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A traditional bandhani-print dupatta with a coordinating kurta set.",
        "is_featured": False,
        "variants": _apparel_variants("HM-BANDHANI", ["S", "M", "L"], ["Pink", "Yellow"]),
    },
    # --- Winter Wear (5) ---
    {
        "name": "Ultra Light Down Puffer Jacket",
        "category": "Winter Wear", "brand": "Uniqlo",
        "base_price": Decimal("5990.00"), "discount_percentage": Decimal("10.00"),
        "description": "A packable puffer jacket with 90% duck down fill, warm at a fraction of the weight.",
        "is_featured": True,
        "variants": _apparel_variants("UNIQLO-PUFFER", ["S", "M", "L", "XL"], ["Black", "Navy"]),
    },
    {
        "name": "Wool Blend Overcoat",
        "category": "Winter Wear", "brand": "H&M",
        "base_price": Decimal("6999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A single-breasted overcoat in a wool blend, tailored for a clean silhouette.",
        "is_featured": False,
        "variants": _apparel_variants("HM-OVERCOAT", ["M", "L", "XL"], ["Camel", "Charcoal"]),
    },
    {
        "name": "Cable Knit Sweater",
        "category": "Winter Wear", "brand": "Zara",
        "base_price": Decimal("2999.00"), "discount_percentage": Decimal("0.00"),
        "description": "A chunky cable-knit sweater in soft brushed yarn.",
        "is_featured": False,
        "variants": _apparel_variants("ZARA-CABLEKNIT", ["S", "M", "L"], ["Cream", "Grey"]),
    },
    {
        "name": "Fleece Zip Hoodie",
        "category": "Winter Wear", "brand": "Adidas",
        "base_price": Decimal("3499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A full-zip fleece hoodie with a brushed interior for warmth.",
        "is_featured": False,
        "variants": _apparel_variants("ADIDAS-FLEECEHOOD", ["M", "L", "XL"], ["Black", "Grey"]),
    },
    {
        "name": "Sherpa Trucker Jacket",
        "category": "Winter Wear", "brand": "Levi's",
        "base_price": Decimal("6499.00"), "discount_percentage": Decimal("5.00"),
        "description": "The classic trucker jacket lined with cozy sherpa fleece.",
        "is_featured": False,
        "variants": _apparel_variants("LEVIS-SHERPA", ["M", "L", "XL"], ["Denim Blue"]),
    },
    # --- Innerwear & Loungewear (5) ---
    {
        "name": "Airism Boxer Briefs (3-Pack)",
        "category": "Innerwear & Loungewear", "brand": "Uniqlo",
        "base_price": Decimal("1490.00"), "discount_percentage": Decimal("0.00"),
        "description": "Breathable, quick-drying boxer briefs, sold as a pack of three.",
        "is_featured": False,
        "variants": _apparel_variants("UNIQLO-BOXER3", ["S", "M", "L"], ["Assorted"]),
    },
    {
        "name": "Cotton Lounge Pants",
        "category": "Innerwear & Loungewear", "brand": "H&M",
        "base_price": Decimal("1299.00"), "discount_percentage": Decimal("0.00"),
        "description": "Relaxed-fit lounge pants in soft brushed cotton with an elastic waistband.",
        "is_featured": False,
        "variants": _apparel_variants("HM-LOUNGEPANT", ["S", "M", "L"], ["Grey", "Navy"]),
    },
    {
        "name": "Ribbed Cami & Shorts Set",
        "category": "Innerwear & Loungewear", "brand": "Zara",
        "base_price": Decimal("1799.00"), "discount_percentage": Decimal("0.00"),
        "description": "A ribbed cami top and matching shorts, made for easy at-home wear.",
        "is_featured": False,
        "variants": _apparel_variants("ZARA-CAMISET", ["XS", "S", "M"], ["Sage", "Blush"]),
    },
    {
        "name": "Seamless Sports Bra",
        "category": "Innerwear & Loungewear", "brand": "Puma",
        "base_price": Decimal("1499.00"), "discount_percentage": Decimal("0.00"),
        "description": "A medium-support seamless sports bra with moisture-wicking fabric.",
        "is_featured": False,
        "variants": _apparel_variants("PUMA-SPORTSBRA", ["S", "M", "L"], ["Black", "Grey"]),
    },
    {
        "name": "Boxerjock Briefs (2-Pack)",
        "category": "Innerwear & Loungewear", "brand": "Under Armour",
        "base_price": Decimal("1599.00"), "discount_percentage": Decimal("0.00"),
        "description": "6-inch inseam boxerjock briefs with an anti-odor finish, pack of two.",
        "is_featured": False,
        "variants": _apparel_variants("UA-BOXERJOCK2", ["S", "M", "L"], ["Black"]),
    },
]


def seed_products(db, categories: dict[str, Category], brands: dict[str, Brand]) -> None:
    for spec in PRODUCTS:
        slug = slugify(spec["name"])
        existing = db.query(Product).filter(Product.slug == slug).first()
        if existing:
            print(f"  [skip] product '{spec['name']}' already exists")
            continue

        product = Product(
            name=spec["name"],
            slug=slug,
            description=spec["description"],
            category_id=categories[spec["category"]].id,
            brand_id=brands[spec["brand"]].id,
            base_price=spec["base_price"],
            discount_percentage=spec["discount_percentage"],
            gst_percentage=Decimal("12.00"),
            # ACTIVE, not the model's default DRAFT — GET /api/v1/products
            # filters on status == ACTIVE (see api/v1/catalog.py), so
            # seeding as DRAFT would insert rows that still never appear
            # on the storefront. This is the exact "empty database" bug
            # from audit item #3, just moved one layer deeper.
            status=ProductStatus.ACTIVE,
            is_featured=spec["is_featured"],
            is_trending=False,
        )
        product.variants = [
            ProductVariant(
                sku=v["sku"],
                size=v["size"],
                color=v["color"],
                stock_quantity=v["stock_quantity"],
            )
            for v in spec["variants"]
        ]
        db.add(product)
        db.commit()
        db.refresh(product)

        # Two images per product: one primary, one secondary — enough for
        # ProductOut.primary_image_url (list/grid view) and the detail
        # page's image gallery to both have real data to render.
        db.add(
            ProductImage(
                product_id=product.id,
                image_url=_generate_placeholder_image(
                    product.id, slug, spec["name"], spec["brand"], spec["category"], "-1"
                ),
                is_primary=True,
                display_order=0,
            )
        )
        db.add(
            ProductImage(
                product_id=product.id,
                image_url=_generate_placeholder_image(
                    product.id, slug, spec["name"], spec["brand"], spec["category"], "-2"
                ),
                is_primary=False,
                display_order=1,
            )
        )
        db.commit()
        print(f"  [ok] created product: {spec['name']} ({len(spec['variants'])} variant(s), 2 image(s))")


def seed_coupons(db) -> None:
    """Optional, per audit item #3's brief — a couple of realistic coupons
    so the cart/checkout flow has something to actually apply."""
    coupons = [
        {
            "code": "WELCOME10",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": Decimal("10.00"),
            "max_discount_amount": Decimal("500.00"),
            "min_order_value": Decimal("999.00"),
        },
        {
            "code": "FLAT200",
            "discount_type": DiscountType.FLAT,
            "discount_value": Decimal("200.00"),
            "max_discount_amount": None,
            "min_order_value": Decimal("1999.00"),
        },
    ]
    for spec in coupons:
        existing = db.query(Coupon).filter(Coupon.code == spec["code"]).first()
        if existing:
            print(f"  [skip] coupon '{spec['code']}' already exists")
            continue
        db.add(Coupon(**spec, usage_limit=None, times_used=0, is_active=True))
        db.commit()
        print(f"  [ok] created coupon: {spec['code']}")


def main() -> None:
    # Fail fast and clearly if the database isn't reachable at all — the
    # same "clear error over a buried traceback" philosophy already used
    # in app/core/config.py._load_settings().
    try:
        with engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 - intentionally broad, this is a CLI entrypoint
        print(
            "\n=== Could not connect to the database ===\n"
            f"{exc}\n\n"
            "Check that DATABASE_URL in backend/.env points at a running "
            "Postgres instance, and that `alembic upgrade head` has already "
            "been run.\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    # Verify migrations have actually been applied — a missing 'users'
    # table means alembic upgrade head hasn't run yet, and every insert
    # below would otherwise fail with a confusing "relation does not
    # exist" instead of a clear instruction.
    # NOTE: Table.exists(bind=...) was removed in SQLAlchemy 2.0 (this
    # project pins sqlalchemy==2.0.35) — inspect(engine).has_table(...) is
    # the current, correct replacement.
    if not inspect(engine).has_table("users"):
        print(
            "\n=== Tables not found ===\n"
            "Run `alembic upgrade head` before `python seed.py` — the "
            "'users' table doesn't exist yet, so migrations haven't been "
            "applied.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    db = SessionLocal()
    try:
        print("Seeding admin user...")
        seed_admin(db)

        print("Seeding categories...")
        categories = seed_categories(db)

        print("Seeding brands...")
        brands = seed_brands(db)

        print("Seeding products, variants, and images...")
        seed_products(db, categories, brands)

        print("Seeding coupons...")
        seed_coupons(db)

        print("\nDone. Fresh install now has data — restart is not required, it's already live.")
        print(f"Admin login -> email: {settings.DEFAULT_ADMIN_EMAIL}  password: {settings.DEFAULT_ADMIN_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""
Public, customer-facing catalog endpoints. No auth required.

WHY ILIKE SEARCH FOR PHASE 2, NOT ELASTICSEARCH:
The brief asks to "choose the better option and explain why" between
ElasticSearch and Postgres full-text search. For THIS phase, we use the
simplest possible thing (SQL ILIKE on name/description) because there's
no data volume yet to justify anything more, and every added moving part
is something that can break. The real production answer, once the catalog
has real volume, is Postgres full-text search (tsvector + GIN index) —
not ElasticSearch — because:
  - It lives in the same database as everything else: no second system to
    keep in sync, no separate ops burden, no eventual-consistency window
    between "product saved" and "product searchable".
  - Postgres FTS supports ranking, stemming, and prefix search, which
    covers "auto-suggest as you type" and typo-tolerant search well
    enough for a catalog in the tens/low hundreds of thousands of SKUs.
  - ElasticSearch earns its cost (a whole separate service to run, deploy,
    and keep in sync via CDC or dual-writes) once you need faceted search
    across millions of products with sub-50ms latency, or search
    features Postgres genuinely can't do well (fuzzy matching at scale,
    complex relevance tuning). That's a Phase 6+ decision, not a Phase 2
    one — introducing it now would be solving a scale problem we don't
    have yet at the cost of real operational complexity today.
This endpoint is written so swapping ILIKE for a tsvector query later is
a change inside this one function, not a rewrite of the API contract.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.catalog import Brand, Category, Product, ProductStatus
from app.schemas.catalog import BrandOut, CategoryOut, PaginatedProducts, ProductDetailOut

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.execute(select(Category).order_by(Category.name)).scalars().all()


@router.get("/brands", response_model=list[BrandOut])
def list_brands(db: Session = Depends(get_db)):
    return db.execute(select(Brand).order_by(Brand.name)).scalars().all()


@router.get("/products", response_model=PaginatedProducts)
def list_products(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None, description="Category slug"),
    brand: str | None = Query(default=None, description="Brand slug"),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    q: str | None = Query(default=None, description="Search term"),
    sort: str = Query(default="newest", pattern="^(newest|price_asc|price_desc|featured)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .options(
            selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images)
        )
    )

    if category:
        stmt = stmt.join(Category).where(Category.slug == category)
    if brand:
        stmt = stmt.join(Brand).where(Brand.slug == brand)
    if min_price is not None:
        stmt = stmt.where(Product.base_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.base_price <= max_price)
    if q:
        like_pattern = f"%{q}%"
        stmt = stmt.where(or_(Product.name.ilike(like_pattern), Product.description.ilike(like_pattern)))

    if sort == "price_asc":
        stmt = stmt.order_by(Product.base_price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Product.base_price.desc())
    elif sort == "featured":
        stmt = stmt.order_by(Product.is_featured.desc(), Product.created_at.desc())
    else:
        stmt = stmt.order_by(Product.created_at.desc())

    # Count total matches (for pagination metadata) using the same filters,
    # without the eager-load options — we only need a count, not rows.
    count_stmt = select(Product.id).where(Product.status == ProductStatus.ACTIVE)
    if category:
        count_stmt = count_stmt.join(Category).where(Category.slug == category)
    if brand:
        count_stmt = count_stmt.join(Brand).where(Brand.slug == brand)
    if min_price is not None:
        count_stmt = count_stmt.where(Product.base_price >= min_price)
    if max_price is not None:
        count_stmt = count_stmt.where(Product.base_price <= max_price)
    if q:
        like_pattern = f"%{q}%"
        count_stmt = count_stmt.where(
            or_(Product.name.ilike(like_pattern), Product.description.ilike(like_pattern))
        )
    total = len(db.execute(count_stmt).scalars().all())

    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()

    return PaginatedProducts(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/products/{slug}", response_model=ProductDetailOut)
def get_product(slug: str, db: Session = Depends(get_db)):
    stmt = (
        select(Product)
        .where(Product.slug == slug, Product.status == ProductStatus.ACTIVE)
        .options(
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.variants),
            selectinload(Product.images),
        )
    )
    product = db.execute(stmt).scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product

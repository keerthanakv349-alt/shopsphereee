"""
Recommendation endpoints: related products and frequently bought together.

WHY "FREQUENTLY BOUGHT TOGETHER" IS A SELF-JOIN ON OrderItem, NOT A
SEPARATE PRECOMPUTED TABLE:
For catalog sizes this build is designed for (a learning project's data
volumes), computing "which other products showed up in the same orders
as this one" live, on every request, is fast enough — it's a single
indexed join. At real e-commerce scale (millions of orders), this same
query would be too slow to run per-request and would move to a scheduled
batch job that precomputes and caches the pairings (e.g. nightly, into a
ProductAssociation table) — noted here as the natural next step, not
built speculatively for data volumes this project doesn't have.

WHY "RELATED PRODUCTS" IS JUST "SAME CATEGORY," NOT A SIMILARITY MODEL:
A real "similar products" feature (visual similarity, attribute
matching, embeddings) needs either a trained model or hand-built
similarity rules — meaningful personalization needs real usage data to
learn from, which a fresh catalog doesn't have yet. Same-category is the
honest, simple version: it's genuinely useful (a customer looking at
sneakers plausibly wants to see other sneakers) without pretending to be
smarter than it is.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.catalog import Product, ProductStatus
from app.models.order import OrderItem
from app.schemas.catalog import ProductOut

router = APIRouter(prefix="/api/v1/products", tags=["recommendations"])


def _load_product_or_404(db: Session, slug: str) -> Product:
    product = db.query(Product).filter(Product.slug == slug).first()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("/{slug}/related", response_model=list[ProductOut])
def get_related_products(slug: str, db: Session = Depends(get_db), limit: int = Query(default=8, le=20)):
    product = _load_product_or_404(db, slug)

    stmt = (
        select(Product)
        .where(
            Product.category_id == product.category_id,
            Product.id != product.id,
            Product.status == ProductStatus.ACTIVE,
        )
        .options(selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images))
        .order_by(Product.is_featured.desc(), Product.created_at.desc())
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()


@router.get("/{slug}/frequently-bought-together", response_model=list[ProductOut])
def get_frequently_bought_together(
    slug: str, db: Session = Depends(get_db), limit: int = Query(default=4, le=10)
):
    product = _load_product_or_404(db, slug)

    # Self-join OrderItem on order_id: for every order that contained THIS
    # product, find every OTHER product in that same order, and count how
    # often each co-occurs.
    a = OrderItem.__table__.alias("a")
    b = OrderItem.__table__.alias("b")

    stmt = (
        select(b.c.product_id, func.count().label("co_occurrence"))
        .select_from(a.join(b, a.c.order_id == b.c.order_id))
        .where(a.c.product_id == product.id, b.c.product_id != product.id, b.c.product_id.is_not(None))
        .group_by(b.c.product_id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    co_occurring_ids = [row[0] for row in db.execute(stmt).all()]
    if not co_occurring_ids:
        return []

    products = (
        db.query(Product)
        .filter(Product.id.in_(co_occurring_ids), Product.status == ProductStatus.ACTIVE)
        .options(selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images))
        .all()
    )
    # Preserve the co-occurrence-ranked order — the DB IN-clause doesn't
    # guarantee it.
    order_index = {pid: i for i, pid in enumerate(co_occurring_ids)}
    products.sort(key=lambda p: order_index.get(p.id, len(order_index)))
    return products

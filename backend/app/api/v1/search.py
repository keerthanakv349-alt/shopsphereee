"""
Search: query logging, autocomplete suggestions, trending searches.

WHY LOGGING IS ITS OWN ENDPOINT, NOT FOLDED INTO GET /products:
The product listing endpoint (catalog.py) is called on every page
render/filter change — including things that AREN'T really "a search"
(clicking a category, changing sort order, paginating). If we logged a
search every time that endpoint ran with a `q` param present, "trending
searches" would be dominated by noise from filter/sort interactions that
happen to carry over a stale query param. Logging only when the frontend
explicitly calls this endpoint — which it does once when the user submits
a search — keeps the trending data meaningful.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import Product, ProductStatus
from app.models.search_log import SearchQuery

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("/log", status_code=204)
def log_search(q: str = Query(min_length=1, max_length=200), db: Session = Depends(get_db)):
    normalized = q.strip().lower()
    if not normalized:
        return None

    existing = db.query(SearchQuery).filter(SearchQuery.query_text == normalized).first()
    if existing:
        existing.search_count += 1
    else:
        db.add(SearchQuery(query_text=normalized))
    db.commit()
    return None


@router.get("/suggestions", response_model=list[str])
def get_suggestions(q: str = Query(min_length=1), db: Session = Depends(get_db)):
    stmt = (
        select(Product.name)
        .where(Product.status == ProductStatus.ACTIVE, Product.name.ilike(f"{q}%"))
        .distinct()
        .limit(5)
    )
    return [row[0] for row in db.execute(stmt).all()]


@router.get("/trending", response_model=list[str])
def get_trending(db: Session = Depends(get_db)):
    top = (
        db.query(SearchQuery.query_text)
        .order_by(SearchQuery.search_count.desc(), SearchQuery.last_searched_at.desc())
        .limit(10)
        .all()
    )
    return [row[0] for row in top]

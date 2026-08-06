"""
Review endpoints.

WHY VERIFIED PURCHASE IS DETECTED SERVER-SIDE, NOT TRUSTED FROM THE CLIENT:
If the frontend just sent "is_verified_purchase: true" as part of the
request body, any customer could claim it for a product they never
bought — the whole point of the badge is that it's NOT self-reported. We
check for a real OrderItem matching this product_id and user_id before
setting it, so the badge only ever reflects something we can actually
verify from our own order history.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.order import OrderItem, Order
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewOut, ReviewSummary

router = APIRouter(prefix="/api/v1", tags=["reviews"])


@router.post("/products/{product_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    product_id: uuid.UUID,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(Review).filter(Review.product_id == product_id, Review.user_id == current_user.id).first()
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "You've already reviewed this product")

    has_purchased = (
        db.query(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.product_id == product_id, Order.user_id == current_user.id)
        .first()
        is not None
    )

    review = Review(
        product_id=product_id,
        user_id=current_user.id,
        rating=payload.rating,
        title=payload.title,
        comment=payload.comment,
        is_verified_purchase=has_purchased,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/products/{product_id}/reviews", response_model=ReviewSummary)
def list_reviews(product_id: uuid.UUID, db: Session = Depends(get_db)):
    reviews = (
        db.query(Review)
        .filter(Review.product_id == product_id)
        .options(selectinload(Review.user))
        .order_by(Review.helpful_count.desc(), Review.created_at.desc())
        .all()
    )
    avg_rating = db.query(func.avg(Review.rating)).filter(Review.product_id == product_id).scalar()

    return ReviewSummary(
        average_rating=round(float(avg_rating), 1) if avg_rating is not None else 0.0,
        review_count=len(reviews),
        reviews=reviews,
    )


@router.post("/reviews/{review_id}/helpful", response_model=ReviewOut)
def mark_helpful(review_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    # Simplification: doesn't track WHO voted, so the same person could
    # click this more than once. A production version would add a
    # ReviewHelpfulVote(review_id, user_id) join table with a unique
    # constraint to prevent that — flagged here rather than silently
    # left out, since it's a real gap, not an oversight.
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    review.helpful_count += 1
    db.commit()
    db.refresh(review)
    return review


@router.post("/reviews/{review_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_review(review_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    review.is_reported = True
    db.commit()
    return None

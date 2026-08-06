import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=150)
    comment: str = Field(min_length=5, max_length=2000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rating: int
    title: str | None
    comment: str
    is_verified_purchase: bool
    helpful_count: int
    created_at: datetime
    reviewer_name: str


class ReviewSummary(BaseModel):
    average_rating: float
    review_count: int
    reviews: list[ReviewOut]

"""
SearchQuery.

WHY WE LOG SEARCHES AT ALL:
"Trending Searches" (an explicit item in the brief) can't be answered
without SOME record of what people searched for. This is deliberately
the simplest possible version: one row per distinct normalized query
text, with a counter incremented on every repeat search — not a
per-search-event log (which would need aggregation queries to answer
"what's trending" instead of a simple ORDER BY). A per-event log would
be needed for time-windowed trending ("trending this week" vs
all-time) — noted as a natural upgrade once this simple version proves
useful, not built speculatively now.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    query_text: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    search_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

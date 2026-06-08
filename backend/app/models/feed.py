import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Float, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FeedCache(Base):
    __tablename__ = "feed_cache"
    __table_args__ = (
        Index("idx_feed_cache_query", "query_key", "fetched_at"),
        Index("idx_feed_cache_hash", "content_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    query_company: Mapped[str] = mapped_column(String(100), nullable=False)
    query_position: Mapped[str] = mapped_column(String(100), nullable=False)
    query_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

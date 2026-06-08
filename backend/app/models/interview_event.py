import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Float, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InterviewEvent(Base):
    __tablename__ = "interview_events"
    __table_args__ = (
        Index("idx_interview_events_company_position", "company", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_document_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_documents.id"), nullable=False)
    company: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    round: Mapped[str | None] = mapped_column(String(50), nullable=True)
    interview_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

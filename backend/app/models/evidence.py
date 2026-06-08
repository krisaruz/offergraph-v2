import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Float, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QuestionEvidence(Base):
    __tablename__ = "question_evidence"
    __table_args__ = (
        Index("idx_question_evidence_question_id", "question_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("interview_questions.id"), nullable=False)
    source_document_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_documents.id"), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

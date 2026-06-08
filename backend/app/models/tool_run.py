import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ToolRun(Base):
    __tablename__ = "tool_runs"
    __table_args__ = (
        Index("idx_tool_runs_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("search_sessions.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(30), nullable=False)
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

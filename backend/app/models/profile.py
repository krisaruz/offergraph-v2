import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    identity: Mapped[str] = mapped_column(String(50), nullable=False)
    directions_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_companies_json: Mapped[str] = mapped_column(Text, nullable=False)
    regions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

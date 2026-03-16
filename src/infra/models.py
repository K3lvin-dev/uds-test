import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SubmissionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    GRADED = "GRADED"
    ERROR = "ERROR"


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str] = mapped_column(String(100), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        String(20), nullable=False, default=SubmissionStatus.PENDING
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    criteria: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    overall_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

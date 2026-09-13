import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SAEnum

from app.models.base import Base
from app.schemas.rule import Effort


class Sentence(Base):
    __tablename__ = "sentences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    judgment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("judgments.id"), nullable=False, index=True
    )
    charge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("charges.id"), nullable=False, index=True
    )

    task: Mapped[str] = mapped_column(String(120), nullable=False)
    target_start: Mapped[int] = mapped_column(Integer, nullable=False)
    target_end: Mapped[int] = mapped_column(Integer, nullable=False)

    effort: Mapped[Effort] = mapped_column(SAEnum(Effort, name="effort"), nullable=False)
    effort_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effort_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    effort_clamped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    advisory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    judgment: Mapped["Judgment"] = relationship(back_populates="sentences")
    charge: Mapped["Charge"] = relationship(back_populates="sentences")

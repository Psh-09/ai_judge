import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 판례 verdict id 목록(plan.md §7: 기소당 3건·사건 전체 10건 상한)으로, 사후 추적을 위해
# 통째로 읽고 쓸 뿐 배열 연산자(포함/중첩 등)로 조회하지 않는다.
# Postgres에서는 네이티브 int[], SQLite 등에서는 JSON으로 저장한다.
_PrecedentIdsType = ARRAY(Integer).with_variant(JSON, "sqlite")


class Judgment(Base):
    __tablename__ = "judgments"
    __table_args__ = (UniqueConstraint("case_id", "revision", name="uq_judgments_case_revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cases.id"), nullable=False, index=True
    )

    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    opinion: Mapped[str] = mapped_column(Text, nullable=False)
    rebuttal_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_overturned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    precedent_verdict_ids: Mapped[list[int]] = mapped_column(
        _PrecedentIdsType, nullable=False, default=list
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped["Case"] = relationship(back_populates="judgments")
    verdicts: Mapped[list["Verdict"]] = relationship(
        back_populates="judgment", cascade="all, delete-orphan"
    )
    sentences: Mapped[list["Sentence"]] = relationship(
        back_populates="judgment", cascade="all, delete-orphan"
    )

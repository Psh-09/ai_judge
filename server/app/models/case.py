import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SAEnum

from app.models.base import Base
from app.models.enums import CaseStatus, FailedStage, FailureReason

_ACTIVE_STATUS_FILTER = "status NOT IN ('SENTENCED', 'DISMISSED', 'FAILED')"


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index(
            "uq_cases_active_code",
            "user_id",
            "code_hash",
            "language",
            unique=True,
            postgresql_where=text(_ACTIVE_STATUS_FILTER),
            sqlite_where=text(_ACTIVE_STATUS_FILTER),
        ),
        Index("ix_cases_status_locked_at", "status", "locked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    code_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    total_lines: Mapped[int] = mapped_column(Integer, nullable=False)

    repo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)

    charges_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[CaseStatus] = mapped_column(
        SAEnum(CaseStatus, name="case_status"),
        nullable=False,
        default=CaseStatus.QUEUED_PROSECUTION,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    appeal_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    prosecution_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    defense_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    judgment_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejudgment_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)

    failed_stage: Mapped[FailedStage | None] = mapped_column(
        SAEnum(FailedStage, name="failed_stage"), nullable=True
    )
    failure_reason: Mapped[FailureReason | None] = mapped_column(
        SAEnum(FailureReason, name="failure_reason"), nullable=True
    )

    rejudgment_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejudgment_failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cases.id"), nullable=True
    )

    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="cases")
    charges: Mapped[list["Charge"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    judgments: Mapped[list["Judgment"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    appeal: Mapped["Appeal | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SAEnum

from app.models.base import Base
from app.schemas.rule import Severity


class Charge(Base):
    __tablename__ = "charges"
    __table_args__ = (UniqueConstraint("case_id", "charge_index", name="uq_charges_case_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cases.id"), nullable=False, index=True
    )

    charge_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_index: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)

    evidence_start: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_end: Mapped[int] = mapped_column(Integer, nullable=False)

    charged_severity: Mapped[Severity] = mapped_column(
        SAEnum(Severity, name="severity"), nullable=False
    )
    severity_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    case: Mapped["Case"] = relationship(back_populates="charges")
    plea: Mapped["Plea | None"] = relationship(
        back_populates="charge", cascade="all, delete-orphan"
    )
    verdicts: Mapped[list["Verdict"]] = relationship(
        back_populates="charge", cascade="all, delete-orphan"
    )
    sentences: Mapped[list["Sentence"]] = relationship(
        back_populates="charge", cascade="all, delete-orphan"
    )

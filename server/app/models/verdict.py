from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SAEnum

from app.models.base import Base
from app.models.enums import VerdictValue
from app.schemas.rule import Severity


class Verdict(Base):
    __tablename__ = "verdicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    judgment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("judgments.id"), nullable=False, index=True
    )
    charge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("charges.id"), nullable=False, index=True
    )

    verdict: Mapped[VerdictValue] = mapped_column(
        SAEnum(VerdictValue, name="verdict_value"), nullable=False
    )
    final_severity: Mapped[Severity | None] = mapped_column(
        SAEnum(Severity, name="severity"), nullable=True
    )
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    judgment: Mapped["Judgment"] = relationship(back_populates="verdicts")
    charge: Mapped["Charge"] = relationship(back_populates="verdicts")

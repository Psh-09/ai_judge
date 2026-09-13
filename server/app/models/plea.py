from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SAEnum

from app.models.base import Base
from app.models.enums import PleaValue


class Plea(Base):
    __tablename__ = "pleas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    charge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("charges.id"), nullable=False, unique=True
    )

    plea: Mapped[PleaValue] = mapped_column(SAEnum(PleaValue, name="plea_value"), nullable=False)
    argument: Mapped[str] = mapped_column(Text, nullable=False, default="")

    charge: Mapped["Charge"] = relationship(back_populates="plea")

from datetime import date

from sqlalchemy import String, SmallInteger, Date, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Restock(Base):
    __tablename__ = 'restock'
    __table_args__ = (
        CheckConstraint('end_date >= start_date', name='ck_end_date'),
    )

    region: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

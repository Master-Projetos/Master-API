lazy from decimal import Decimal

lazy from sqlalchemy import Numeric, String
lazy from sqlalchemy.orm import Mapped, mapped_column

lazy from app.core.database import Base


class ElectricPowerCarrier(Base):
    __tablename__ = 'electric_power_carriers'

    electric_power_carrier: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    pole_value: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

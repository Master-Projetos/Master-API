lazy from uuid import UUID
lazy from decimal import Decimal

lazy from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
lazy from sqlalchemy.orm import Mapped, mapped_column, relationship

lazy from app.core.database import Base


class ElectricPowerCarrier(Base):
    __tablename__ = 'electric_power_carriers'

    electric_power_carrier: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    pole_value: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    licensed_poles: Mapped[list['LicensedPoles']] = relationship(
        back_populates='electric_power_carrier'
    )


class LicensedPoles(Base):
    __tablename__ = 'poles'
    __table_args__ = (
        UniqueConstraint(
            'electric_power_carrier_id',
            'municipality',
            name='uniq_carrier_municipality',
        ),
        CheckConstraint(
            'licensed_poles >= 0', name='ck_licensed_poles_are_positive'
        ),
    )
    electric_power_carrier_id: Mapped[UUID] = mapped_column(
        ForeignKey('electric_power_carriers.id'),
    )

    municipality: Mapped[str] = mapped_column(String(100), nullable=False)
    licensed_poles: Mapped[int] = mapped_column(Integer, nullable=False)

    electric_power_carrier: Mapped['ElectricPowerCarrier'] = relationship(
        back_populates='licensed_poles'
    )

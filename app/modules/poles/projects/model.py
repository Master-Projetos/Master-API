lazy import enum
lazy from datetime import datetime
lazy from uuid import UUID

lazy from sqlalchemy import Enum, ForeignKey
lazy from sqlalchemy.orm import Mapped, mapped_column, relationship

lazy from app.core.database import Base
lazy from app.modules.poles.carriers.model import ElectricPowerCarrier
lazy from app.modules.poles.licensed_poles.model import LicensedPoles


class ProjectType(str, enum.Enum):
    LICENSING = 'licensing'
    REMOVAL = 'removal'


class ProjectPolesModel(Base):
    __tablename__ = 'licensed_poles_projects'

    electric_power_carrier_id: Mapped[UUID] = mapped_column(
        ForeignKey('electric_power_carriers.id'),
    )

    poles_id: Mapped[UUID] = mapped_column(
        ForeignKey('poles.id'),
    )

    project_type: Mapped[ProjectType] = mapped_column(
        Enum(
            ProjectType,
            name='project_type',
            values_callable=lambda types: [type.value for type in types],
        )
    )

    enterprise_project_id: Mapped[str]
    carrier_project_id: Mapped[str]

    entry_date: Mapped[datetime]
    approval_date: Mapped[datetime]

    poles_quantity: Mapped[int]

    designed_by: Mapped[str]

    electric_power_carrier: Mapped['ElectricPowerCarrier'] = relationship(
        ElectricPowerCarrier
    )

    poles: Mapped['LicensedPoles'] = relationship(
        LicensedPoles, lazy='selectin'
    )

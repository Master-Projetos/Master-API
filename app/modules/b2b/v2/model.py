lazy from datetime import datetime

lazy from app.core.database import Base
lazy from sqlalchemy.orm import Mapped, mapped_column


class B2bModel(Base):
    __tablename__ = 'b2b_projects'

    client: Mapped[str]
    team: Mapped[str]
    sector: Mapped[str]
    requester: Mapped[str]
    priority: Mapped[str]
    report_link: Mapped[str]
    status: Mapped[str]
    situation: Mapped[str]
    month: Mapped[datetime]
    sla_deadline: Mapped[datetime]
    value: Mapped[float]
    approved: Mapped[bool] = mapped_column(default=False)

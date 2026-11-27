from uuid import UUID
lazy from datetime import datetime

lazy from pydantic import BaseModel, ConfigDict, Field

from app.api.v2.modules.poles.licensed_poles.schemas import LicensedPolesGet
from app.modules.poles.projects.model import ProjectType


class ProjectPolesCreate(BaseModel):
    electric_power_carrier_id: UUID
    poles_id: UUID
    project_type: ProjectType
    enterprise_project_id: str
    carrier_project_id: str
    entry_date: datetime
    approval_date: datetime
    poles_quantity: int = Field(gt=0)
    designed_by: str


class ProjectPolesUpdate(BaseModel):
    electric_power_carrier_id: UUID | None = None
    poles_id: UUID | None = None
    project_type: ProjectType | None = None
    enterprise_project_id: str | None = None
    carrier_project_id: str | None = None
    entry_date: datetime | None = None
    approval_date: datetime | None = None
    poles_quantity: int | None = Field(default=None, gt=0)
    designed_by: str | None = None


class ProjectPolesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    electric_power_carrier_id: UUID
    project_type: ProjectType
    enterprise_project_id: str
    carrier_project_id: str
    entry_date: datetime
    approval_date: datetime
    poles_quantity: int
    designed_by: str
    poles: LicensedPolesGet

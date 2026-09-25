from pydantic import BaseModel


class Item(BaseModel):
    deadline: str | None
    client: str
    requester: str | None
    priority: str | None
    region: str
    start_date: str | None
    end_date: str | None
    remaining_days: int | None
    sector: str | None


class ProjectValue(Item):
    value: float


class FinancialSummary(BaseModel):
    total_value: float
    average_value: float
    highest_value: float
    lowest_value: float
    approved_value: float
    highest_project: ProjectValue | None
    highest_approved_project: ProjectValue | None
    approved_projects: list[ProjectValue]
    unapproved_projects: list[ProjectValue]


class Deadline(BaseModel):
    counts: dict[str, int]
    items: list[Item]


class StatusItem(Item):
    status: str


class Status(BaseModel):
    counts: dict[str, int]
    items: list[StatusItem]


class StatusByRegion(BaseModel):
    counts: dict[str, dict[str, int]]
    items: list[StatusItem]


class PriorityByRequester(BaseModel):
    counts: dict[str, dict[str, int]]
    items: list[Item]


class MonthItem(Item):
    month: str


class ProjectsByMonth(BaseModel):
    counts: dict[str, int]
    items: list[MonthItem]


class B2BDashboard(BaseModel):
    priority: dict[str, int]
    status: Status
    financial: FinancialSummary
    status_by_region: StatusByRegion
    priority_by_requester: PriorityByRequester
    projects_by_month: ProjectsByMonth
    deadline: Deadline

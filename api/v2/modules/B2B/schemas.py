from pydantic import BaseModel


class FinancialSummary(BaseModel):
    total_value: float
    average_value: float
    highest_value: float
    lowest_value: float
    approved_value: float


class B2BDashboard(BaseModel):
    priority: dict[str, int]
    status: dict[str, int]
    financial: FinancialSummary
    status_by_region: dict[str, dict[str, int]]
    priority_by_requester: dict[str, dict[str, int]]
    projects_by_month: dict[str, int]
    deadline: dict[str, int]

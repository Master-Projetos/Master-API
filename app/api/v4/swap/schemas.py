from datetime import date
from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal['checked', 'missing_info', 'unchecked']


class SwapItem(BaseModel):
    section: str
    contract_id: int
    partner: str | None
    contract_url: str | None
    contract_status: str | None
    notes: str | None
    term: str | None
    assignment: str | None
    circuit: str | None
    agreement: str | None
    quantity: str | None
    distance_km: float | None
    fiber_km: float | None
    status: str | None
    signed_at: date | None
    ends_at: date | None
    check_status: CheckStatus


class SwapSummary(BaseModel):
    total_circuits: int
    total_contracts: int
    total_partners: int
    total_fiber_km: float


class SwapDashboard(BaseModel):
    summary: SwapSummary
    check_counts: dict[CheckStatus, int]
    by_section: dict[str, dict[CheckStatus, int]]
    by_partner: dict[str, dict[CheckStatus, int]]
    items: list[SwapItem]

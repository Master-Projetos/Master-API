from datetime import date

from pydantic import BaseModel

from app.api.v4.swap.schemas import CheckStatus


# Only what the panel (the Front repo) reads, in v4's formats: it stores
# each item and flags every field that changes
class SwapItem(BaseModel):
    section: str
    contract_id: int | None
    partner: str | None
    contract_status: str | None
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


class SwapList(BaseModel):
    items: list[SwapItem]

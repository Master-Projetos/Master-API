from datetime import date

from pydantic import BaseModel


class StockItem(BaseModel):
    site: str
    code: str
    description: str
    unit: str | None
    min_stock: int | None
    safe_stock: int | None
    balance: int | None
    alert: bool | None
    critical_alert: bool | None
    total: int | None


class StockSummary(BaseModel):
    total_items: int
    total_sites: int
    alert_rows: int
    critical_alert_rows: int


class StockDashboard(BaseModel):
    summary: StockSummary
    alerts_by_site: dict[str, dict[str, int]]
    items: list[StockItem]


class RestockWindow(BaseModel):
    start: date
    end: date


class RestockMonth(BaseModel):
    month: int
    label: str
    text: str | None
    windows: list[RestockWindow]


class RestockRegion(BaseModel):
    region: str
    months: list[RestockMonth]


class RestockSchedule(BaseModel):
    year: int
    regions: list[RestockRegion]

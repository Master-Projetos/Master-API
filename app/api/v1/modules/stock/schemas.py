from datetime import date
from typing import Any

from pydantic import BaseModel


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


# The columns come straight from the sheet, so rows are free-form
class StockSheets(BaseModel):
    sheets: dict[str, list[dict[str, Any]]]


class StockConfigItem(BaseModel):
    code: str | None
    description: str
    unit: str | None
    min_stock: int | None
    safe_stock: int | None

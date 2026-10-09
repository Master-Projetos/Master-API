from typing import Any

from pydantic import BaseModel


# The columns come straight from the sheet, so rows are free-form
class StockSheets(BaseModel):
    sheets: dict[str, list[dict[str, Any]]]


class StockConfigItem(BaseModel):
    code: str | None
    description: str
    unit: str | None
    min_stock: int | None
    safe_stock: int | None

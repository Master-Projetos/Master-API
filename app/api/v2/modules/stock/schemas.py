from datetime import date

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

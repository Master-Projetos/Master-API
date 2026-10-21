from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RestockBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, validate_assignment=True)

    region: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def validate_data_range(self):
        if self.start_date > self.end_date:
            raise ValueError('end_date must be before start_date')
        return self


class RestockGet(RestockBase):
    id: UUID


class RestockCreate(RestockBase):
    pass


class RestockUpdate(BaseModel):
    region: str | None = Field(default=None, min_length=1, max_length=100)
    start_date: date | None = None
    end_date: date | None = None

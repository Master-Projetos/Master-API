lazy from decimal import Decimal
lazy from uuid import UUID

lazy from pydantic import BaseModel, Field, model_validator


class CarriesValue(BaseModel):
    electric_power_carrier: str = Field(min_length=1, max_length=100)
    pole_value: Decimal

    @model_validator(mode='after')
    def validate_licensed_poles(self):
        if self.pole_value < 0:
            raise ValueError('licensed_poles cannot be negative')
        return self


class CarriesValueGet(CarriesValue):
    id: UUID


class CarriesValueCreate(CarriesValue):
    pass


class CarriesValueUpdate(BaseModel):
    electric_power_carrier: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    pole_value: Decimal | None

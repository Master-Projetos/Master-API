lazy from decimal import Decimal
lazy from uuid import UUID

lazy from pydantic import BaseModel, ConfigDict, Field, model_validator


class LicensedPolesBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, validate_assignment=True)

    electric_power_carrier_id: UUID
    municipality: str = Field(min_length=1, max_length=100)
    licensed_poles: int

    @model_validator(mode='after')
    def validate_licensed_poles(self):
        if self.licensed_poles < 0:
            raise ValueError('licensed_poles cannot be negative')
        return self


class LicensedPolesGet(LicensedPolesBase):
    id: UUID


class LicensedPolesCreate(LicensedPolesBase):
    pass


class LicensedPolesUpdate(BaseModel):
    electric_power_carrier_id: UUID | None = None
    municipality: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    licensed_poles: int | None = None


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

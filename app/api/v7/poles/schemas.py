from pydantic import BaseModel


class CityPoles(BaseModel):
    city: str
    # Only for utilities read from the project mapping (CEMIG)
    projects: int | None
    rent_per_pole: float | None
    licensed_poles: int
    licensed_rent: float | None
    # Estimated from the network length; None when the sheet has no estimate
    network_poles: int | None
    unlicensed_poles: int | None
    unlicensed_rent: float | None


class UtilityPoles(BaseModel):
    utility: str
    rent_per_pole: float | None
    licensed_poles: int
    licensed_rent: float | None
    unlicensed_poles: int
    unlicensed_rent: float | None
    # Licensed + irregular poles the network occupies
    occupied_poles: int | None
    occupied_rent: float | None
    cities: list[CityPoles]

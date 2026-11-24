lazy from datetime import datetime
from decimal import Decimal

lazy from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class B2bCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
                    'client': 'Octane',
                    'team': 'Forever Platinums',
                    'sector': 'Blue Team',
                    'requester': 'Dude',
                    'report_link': 'www.url.com',
                    'status': 'Still on platinium',
                    'situation': '10 games, 0 wins',
                    'month': '10/10/10',
                    'sla_deadline': '11/10/10',
                    'value': 5.0,
                    'approved': 'B2B',
                }
            ]
        }
    )

    client: str = Field(min_length=3, max_length=100)
    team: str
    sector: str = Field(min_length=2, max_length=50)
    priority: str
    requester: str = Field(min_length=3, max_length=25)
    report_link: AnyUrl
    status: str
    situation: str = Field(min_length=5)
    month: datetime
    sla_deadline: datetime
    value: Decimal = Field(max_digits=12, decimal_places=2, ge=0)
    approved: bool = False


class B2bUpdate(BaseModel):
    client: str | None = Field(default=None, min_length=3, max_length=100)
    team: str | None = None
    sector: str | None = Field(default=None, min_length=2, max_length=50)
    priority: str | None = None
    requester: str | None = Field(default=None, min_length=3, max_length=25)
    report_link: AnyUrl | None = None
    status: str | None = None
    situation: str | None = Field(default=None, min_length=5)
    month: datetime | None = None
    sla_deadline: datetime | None = None
    value: Decimal | None = Field(
        default=None, max_digits=12, decimal_places=2, ge=0
    )
    approved: bool | None = None

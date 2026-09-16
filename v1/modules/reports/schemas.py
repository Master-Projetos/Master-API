from pydantic import BaseModel

class ReportSchema(BaseModel):
    status: str
    relatory: str
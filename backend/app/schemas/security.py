from pydantic import BaseModel, Field


class ReportSuspiciousActivityRequest(BaseModel):
    report_token: str = Field(min_length=10)


class ReportSuspiciousActivityResponse(BaseModel):
    success: bool
    code: str
    message: str
    status: str | None = None
    force_relogin: bool | None = None
    blocked_until: str | None = None
    remaining_seconds: int | None = None

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RecoveryCodesStatusResponse(BaseModel):
    success: bool
    total_codes: int
    codes_restants: int
    codes_utilises: int
    message: str


class RecoveryCodesRegenerateRequest(BaseModel):
    mot_de_passe: str = Field(min_length=1)
    code_totp: str = Field(min_length=4, max_length=20)


class RecoveryCodesRegenerateResponse(BaseModel):
    success: bool
    code: str
    message: str
    recovery_codes: list[str]


class RecoveryCodesEmailRequest(BaseModel):
    recovery_codes: list[str]


class RecoveryCodesEmailResponse(BaseModel):
    success: bool
    message: str


class UserActivityItem(BaseModel):
    id: str
    type: str
    description: str
    date: datetime
    adresse_ip: Optional[str]
    user_agent: Optional[str]
    status: str
    details: Optional[dict] = {}


class UserActivityResponse(BaseModel):
    success: bool
    activities: List[UserActivityItem]
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class PasswordResetRequestPayload(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    success: bool
    code: str
    message: str
    reset_link_debug: Optional[str] = None


class PasswordResetVerifyRequest(BaseModel):
    token: str = Field(min_length=20)


class PasswordResetVerifyResponse(BaseModel):
    success: bool
    code: str
    message: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    reset_mfa_token: Optional[str] = None
    requires_mfa: bool = True


class PasswordResetTotpVerifyRequest(BaseModel):
    reset_mfa_token: str = Field(min_length=10)
    code: str = Field(default="", max_length=20)


class PasswordResetRecoveryCodeVerifyRequest(BaseModel):
    reset_mfa_token: str = Field(min_length=10)
    code_secours: str = Field(default="", max_length=30)


class PasswordResetRecoveryTokenVerifyRequest(BaseModel):
    token: str = Field(min_length=10)
    code_secours: str = Field(default="", max_length=30)


class PasswordResetMfaVerifyResponse(BaseModel):
    success: bool
    code: str
    message: str
    reset_password_token: Optional[str] = None
    temps_restant: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    attempts: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    remaining_seconds: Optional[int] = None
    recovery_method: Optional[str] = None
    mail_sent: Optional[bool] = None


class PasswordResetCompleteRequest(BaseModel):
    reset_password_token: str = Field(min_length=10)
    nouveau_mot_de_passe: str = Field(min_length=1, max_length=256)
    confirmation_mot_de_passe: str = Field(min_length=1, max_length=256)


class PasswordResetCompleteResponse(BaseModel):
    success: bool
    code: str
    message: str
    redirect_to: str = "/login"

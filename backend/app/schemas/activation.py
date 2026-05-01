from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ActivationVerifyResponse(BaseModel):
    success: bool
    code: str
    message: str
    email: Optional[EmailStr] = None


class ActivationCompleteRequest(BaseModel):
    token: str = Field(min_length=20)
    nouveau_mot_de_passe: str = Field(min_length=1, max_length=256)
    confirmation_mot_de_passe: str = Field(min_length=1, max_length=256)


class ActivationCompleteResponse(BaseModel):
    success: bool
    code: str
    message: str
    email: EmailStr
    next_step: str
    totp_setup_token: str


class ActivationResendRequest(BaseModel):
    email: EmailStr


class ActivationResendResponse(BaseModel):
    success: bool
    code: str
    message: str


class TotpSetupStartRequest(BaseModel):
    totp_setup_token: str = Field(min_length=10)


class TotpSetupStartResponse(BaseModel):
    success: bool
    code: str
    message: str
    email: EmailStr
    secret: str
    otpauth_url: str
    qr_code_base64: str


class TotpSetupVerifyRequest(BaseModel):
    totp_setup_token: str = Field(min_length=10)
    code: str = Field(min_length=4, max_length=20)


class TotpSetupVerifyResponse(BaseModel):
    success: bool
    code: str
    message: str
    email: EmailStr
    recovery_codes: list[str] = []
    redirect_to: str = "/login"
    temps_restant: Optional[str] = None
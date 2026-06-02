from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str | None = None
    mot_de_passe: str | None = None


class LoginResponse(BaseModel):
    success: bool
    code: str
    message: str
    status: Optional[str] = None
    reason: Optional[str] = None
    remaining_seconds: Optional[int] = None
    expires_in_seconds: Optional[int] = None
    mail_sent: Optional[bool] = None
    mfa_token: Optional[str] = None
    setup_token: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    can_request_reactivation: Optional[bool] = None
    redirect_to: Optional[str] = None
    temps_restant: Optional[str] = None


class TotpVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=10)
    code: str = Field(default="", max_length=20)


class RecoveryCodeVerifyRequest(BaseModel):
    mfa_token: Optional[str] = Field(default=None, min_length=10)
    code_secours: Optional[str] = None
    recovery_code: Optional[str] = None


class MfaBackupCodeLinkVerifyRequest(BaseModel):
    token: str = Field(min_length=10)
    code_secours: str = ""


class MfaResetRecoveryCodeVerifyRequest(BaseModel):
    token: str = Field(min_length=10)
    recovery_code: str = ""


class MfaResetConfirmRequest(BaseModel):
    token: str = Field(min_length=10)
    code: str = Field(default="", max_length=20)


class MfaSetupStartRequest(BaseModel):
    setup_token: str = Field(min_length=10)


class MfaSetupConfirmRequest(BaseModel):
    setup_token: str = Field(min_length=10)
    code: str = Field(default="", max_length=20)


class SecureRecoveryCompleteRequest(BaseModel):
    token: str = Field(min_length=10)


class RecoverySupervisorActionRequest(BaseModel):
    token: str = Field(min_length=10)
    action: str = ""


class AccountReactivationRequest(BaseModel):
    email: EmailStr


class AccountReactivationActionRequest(BaseModel):
    token: str = Field(min_length=10)
    action: str = ""


class AuthTokenResponse(BaseModel):
    success: bool
    code: str
    message: str
    status: Optional[str] = None
    reason: Optional[str] = None
    attempts: Optional[int] = None
    remaining_seconds: Optional[int] = None
    mail_sent: Optional[bool] = None
    email_sent: Optional[bool] = None
    supervisor_mail_sent: Optional[bool] = None
    can_use_backup_code: Optional[bool] = None
    can_reset_mfa: Optional[bool] = None
    expires_in_seconds: Optional[int] = None
    otpauth_uri: Optional[str] = None
    qr_code: Optional[str] = None
    qr_code_base64: Optional[str] = None
    setup_token: Optional[str] = None
    recovery_codes: list[str] = []
    access_token: Optional[str] = None
    token_type: str = "bearer"
    role: Optional[str] = None
    user: Optional[dict] = None
    redirect_to: Optional[str] = None
    temps_restant: Optional[str] = None


class CurrentUserResponse(BaseModel):
    id: UUID
    email: EmailStr
    nom_complet: str
    est_actif: bool
    role: str
    statut_compte: str
    departement_nom: Optional[str] = None
    permissions: list[str] = []
    date_creation: Optional[datetime] = None
    date_derniere_connexion: Optional[datetime] = None


class LogoutResponse(BaseModel):
    success: bool
    message: str

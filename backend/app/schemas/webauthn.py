from typing import Any, Optional

from pydantic import BaseModel, Field


class WebAuthnRegisterStartRequest(BaseModel):
    nom_appareil: str = Field(min_length=2, max_length=150)


class WebAuthnRegisterStartResponse(BaseModel):
    success: bool
    code: str
    message: str
    options: dict[str, Any]
    webauthn_register_token: str


class WebAuthnRegisterVerifyRequest(BaseModel):
    webauthn_register_token: str
    credential: dict[str, Any]


class WebAuthnRegisterVerifyResponse(BaseModel):
    success: bool
    code: str
    message: str


class WebAuthnSensitiveStartResponse(BaseModel):
    success: bool
    code: str
    message: str
    options: dict[str, Any]
    webauthn_action_token: str


class WebAuthnSensitiveVerifyRequest(BaseModel):
    webauthn_action_token: str
    credential: dict[str, Any] = {}


class WebAuthnSensitiveVerifyResponse(BaseModel):
    success: bool
    code: str
    message: str
    sensitive_action_token: Optional[str] = None
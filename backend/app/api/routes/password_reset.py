from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.password_reset import (
    PasswordResetCompleteRequest,
    PasswordResetCompleteResponse,
    PasswordResetMfaVerifyResponse,
    PasswordResetRecoveryCodeVerifyRequest,
    PasswordResetRecoveryTokenVerifyRequest,
    PasswordResetRequestPayload,
    PasswordResetRequestResponse,
    PasswordResetTotpVerifyRequest,
    PasswordResetVerifyRequest,
    PasswordResetVerifyResponse,
)
from app.services.password_reset_service import PasswordResetService

router = APIRouter(prefix="/auth/password-reset", tags=["Mot de passe oublié"])


def get_client_context(request: Request):
    adresse_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return adresse_ip, user_agent


def get_password_reset_service(
    db: Session = Depends(get_db),
) -> PasswordResetService:
    return PasswordResetService(db)


@router.post("/request", response_model=PasswordResetRequestResponse)
def request_password_reset(
    payload: PasswordResetRequestPayload,
    request: Request,
    service: PasswordResetService = Depends(get_password_reset_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.request_reset(
        email=str(payload.email),
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/verify", response_model=PasswordResetVerifyResponse)
def verify_password_reset_token(
    payload: PasswordResetVerifyRequest,
    request: Request,
    service: PasswordResetService = Depends(get_password_reset_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_token(
        token=payload.token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/totp/verify", response_model=PasswordResetMfaVerifyResponse)
def verify_password_reset_totp(
    payload: PasswordResetTotpVerifyRequest,
    request: Request,
    service: PasswordResetService = Depends(get_password_reset_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_totp(
        reset_mfa_token=payload.reset_mfa_token,
        code=payload.code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/recovery-code/verify", response_model=PasswordResetMfaVerifyResponse)
def verify_password_reset_recovery_code(
    payload: PasswordResetRecoveryCodeVerifyRequest,
    request: Request,
    service: PasswordResetService = Depends(get_password_reset_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_recovery_code(
        reset_mfa_token=payload.reset_mfa_token,
        code_secours=payload.code_secours,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/recovery-token/verify", response_model=PasswordResetMfaVerifyResponse)
def verify_password_reset_recovery_token(
    payload: PasswordResetRecoveryTokenVerifyRequest,
    request: Request,
    service: PasswordResetService = Depends(get_password_reset_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_recovery_token(
        token=payload.token,
        code_secours=payload.code_secours,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/complete", response_model=PasswordResetCompleteResponse)
def complete_password_reset(
    payload: PasswordResetCompleteRequest,
    request: Request,
    service: PasswordResetService = Depends(get_password_reset_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.complete_reset(
        reset_password_token=payload.reset_password_token,
        nouveau_mot_de_passe=payload.nouveau_mot_de_passe,
        confirmation_mot_de_passe=payload.confirmation_mot_de_passe,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )

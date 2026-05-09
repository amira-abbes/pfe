from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.utilisateur import Utilisateur
from app.schemas.account_security import (
    RecoveryCodesEmailRequest,
    RecoveryCodesEmailResponse,
    RecoveryCodesRegenerateRequest,
    RecoveryCodesRegenerateResponse,
    RecoveryCodesStatusResponse,
    UserActivityResponse,
)
from app.services.account_security_service import AccountSecurityService

router = APIRouter(prefix="/auth/security", tags=["Sécurité compte"])


def get_client_context(request: Request):
    adresse_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return adresse_ip, user_agent


def get_account_security_service(
    db: Session = Depends(get_db),
) -> AccountSecurityService:
    return AccountSecurityService(db)


@router.get("/recovery-codes/status", response_model=RecoveryCodesStatusResponse)
def recovery_codes_status(
    current_user: Utilisateur = Depends(get_current_user),
    service: AccountSecurityService = Depends(get_account_security_service),
):
    return service.get_recovery_codes_status(current_user)


@router.post(
    "/recovery-codes/regenerate",
    response_model=RecoveryCodesRegenerateResponse,
)
def regenerate_recovery_codes(
    payload: RecoveryCodesRegenerateRequest,
    request: Request,
    current_user: Utilisateur = Depends(get_current_user),
    service: AccountSecurityService = Depends(get_account_security_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.regenerate_recovery_codes(
        user=current_user,
        mot_de_passe=payload.mot_de_passe,
        code_totp=payload.code_totp,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post(
    "/recovery-codes/email",
    response_model=RecoveryCodesEmailResponse,
)
def email_recovery_codes(
    payload: RecoveryCodesEmailRequest,
    request: Request,
    current_user: Utilisateur = Depends(get_current_user),
    service: AccountSecurityService = Depends(get_account_security_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.send_recovery_codes_by_email(
        user=current_user,
        recovery_codes=payload.recovery_codes,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.get("/activity", response_model=UserActivityResponse)
def get_user_activity(
    current_user: Utilisateur = Depends(get_current_user),
    service: AccountSecurityService = Depends(get_account_security_service),
):
    return service.get_user_activity(current_user)
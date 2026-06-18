from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_permissions
from app.db.database import get_db
from app.models.utilisateur import Utilisateur
from app.schemas.auth import (
    AuthTokenResponse,
    AccountReactivationActionRequest,
    AccountReactivationRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    MfaBackupCodeLinkVerifyRequest,
    MfaResetConfirmRequest,
    MfaResetRecoveryCodeVerifyRequest,
    MfaSetupConfirmRequest,
    MfaSetupStartRequest,
    RecoverySupervisorActionRequest,
    LogoutResponse,
    RecoveryCodeVerifyRequest,
    SecureRecoveryCompleteRequest,
    SuperAdminReactivationResendRequest,
    TotpVerifyRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(tags=["Authentification"])


def get_client_context(request: Request) -> tuple[str | None, str | None]:
    adresse_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return adresse_ip, user_agent


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/auth/login", response_model=LoginResponse)
@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    password = payload.password or payload.mot_de_passe or ""

    return service.login(
        email=str(payload.email),
        password=password,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/totp/verify", response_model=AuthTokenResponse)
def verify_totp(
    payload: TotpVerifyRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_totp_login(
        mfa_token=payload.mfa_token,
        code=payload.code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/recovery-code/verify", response_model=AuthTokenResponse)
def verify_recovery_code(
    payload: RecoveryCodeVerifyRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_recovery_code_login(
        mfa_token=payload.mfa_token,
        code_secours=payload.code_secours or payload.recovery_code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/mfa/recovery-code/verify-link", response_model=AuthTokenResponse)
def verify_mfa_recovery_code_link(
    payload: MfaBackupCodeLinkVerifyRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_admin_mfa_backup_code_link(
        token=payload.token,
        code_secours=payload.code_secours,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/mfa/reset/recovery-code/verify", response_model=AuthTokenResponse)
def verify_mfa_reset_recovery_code(
    payload: MfaResetRecoveryCodeVerifyRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_admin_mfa_reset_recovery_code(
        token=payload.token,
        recovery_code=payload.recovery_code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/mfa/reset/confirm", response_model=AuthTokenResponse)
def confirm_mfa_reset(
    payload: MfaResetConfirmRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.confirm_admin_mfa_reset(
        token=payload.token,
        code=payload.code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/mfa/setup/start", response_model=AuthTokenResponse)
def start_mfa_setup(
    payload: MfaSetupStartRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.start_super_admin_mfa_setup(
        setup_token=payload.setup_token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/mfa/setup/confirm", response_model=AuthTokenResponse)
def confirm_mfa_setup(
    payload: MfaSetupConfirmRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.confirm_super_admin_mfa_setup(
        setup_token=payload.setup_token,
        code=payload.code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/secure-recovery/complete", response_model=AuthTokenResponse)
def complete_secure_recovery(
    payload: SecureRecoveryCompleteRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.complete_super_admin_secure_recovery(
        token=payload.token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/recovery-codes/regenerate-link")
def regenerate_recovery_codes_from_link(
    payload: SecureRecoveryCompleteRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.regenerate_recovery_codes_from_link(
        token=payload.token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/recovery-codes/supervisor-action")
def execute_recovery_supervisor_action(
    payload: RecoverySupervisorActionRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.execute_recovery_supervisor_action(
        token=payload.token,
        action=payload.action,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/account-reactivation/request")
def request_account_reactivation(
    payload: AccountReactivationRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.request_account_reactivation(
        email=str(payload.email),
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/account-reactivation/action")
def execute_account_reactivation_action(
    payload: AccountReactivationActionRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.execute_account_reactivation_action(
        token=payload.token,
        action=payload.action,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/auth/super-admin-reactivation/resend")
def resend_super_admin_reactivation_link(
    payload: SuperAdminReactivationResendRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.resend_super_admin_reactivation_link(
        token=payload.token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.get("/auth/me", response_model=CurrentUserResponse)
def me(current_user: Utilisateur = Depends(get_current_user)):
    permissions = get_user_permissions(current_user)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "nom_complet": current_user.nom_complet,
        "est_actif": current_user.est_actif,
        "role": current_user.role,
        "statut_compte": current_user.statut_compte,
        "departement_nom": (
            current_user.departement.nom_departement
            if current_user.departement
            else None
        ),
        "permissions": permissions,
        "date_creation": current_user.date_creation,
        "date_derniere_connexion": current_user.date_derniere_connexion,
    }


@router.post("/auth/logout", response_model=LogoutResponse)
def logout(
    current_user: Utilisateur = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return service.logout(current_user)

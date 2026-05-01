import hashlib

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import decode_scoped_token
from app.db.database import get_db
from app.models.notification_securite import NotificationSecurite
from app.models.utilisateur import Utilisateur
from app.schemas.activation import (
    ActivationCompleteRequest,
    ActivationCompleteResponse,
    ActivationResendRequest,
    ActivationResendResponse,
    ActivationVerifyResponse,
    TotpSetupStartRequest,
    TotpSetupStartResponse,
    TotpSetupVerifyRequest,
    TotpSetupVerifyResponse,
)
from app.services.activation_service import ActivationService
from app.services.mail_service import MailService

router = APIRouter(prefix="/auth/activation", tags=["Activation compte"])


def get_client_context(request: Request):
    adresse_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return adresse_ip, user_agent


def get_activation_service(db: Session = Depends(get_db)) -> ActivationService:
    return ActivationService(db)


@router.get("/verify", response_model=ActivationVerifyResponse)
def verify_activation_token(
    token: str,
    request: Request,
    service: ActivationService = Depends(get_activation_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_activation_token(
        token=token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/complete", response_model=ActivationCompleteResponse)
def complete_activation(
    payload: ActivationCompleteRequest,
    request: Request,
    service: ActivationService = Depends(get_activation_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.complete_activation_password(
        token=payload.token,
        nouveau_mot_de_passe=payload.nouveau_mot_de_passe,
        confirmation_mot_de_passe=payload.confirmation_mot_de_passe,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/resend", response_model=ActivationResendResponse)
def resend_activation_link(
    payload: ActivationResendRequest,
    request: Request,
    service: ActivationService = Depends(get_activation_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.resend_activation_link(
        email=str(payload.email),
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post("/totp/setup/start", response_model=TotpSetupStartResponse)
def start_totp_setup(
    payload: TotpSetupStartRequest,
    service: ActivationService = Depends(get_activation_service),
):
    return service.start_totp_setup(
        totp_setup_token=payload.totp_setup_token,
    )


@router.post("/totp/setup/verify", response_model=TotpSetupVerifyResponse)
def verify_totp_setup(
    payload: TotpSetupVerifyRequest,
    request: Request,
    service: ActivationService = Depends(get_activation_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.verify_totp_setup(
        totp_setup_token=payload.totp_setup_token,
        code=payload.code,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


class ActivationRecoveryCodesEmailRequest(BaseModel):
    totp_setup_token: str
    recovery_codes: list[str]


class ActivationRecoveryCodesEmailResponse(BaseModel):
    success: bool
    message: str
    already_sent: bool = False


@router.post(
    "/recovery-codes/email",
    response_model=ActivationRecoveryCodesEmailResponse,
)
def email_activation_recovery_codes(
    payload: ActivationRecoveryCodesEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    adresse_ip, user_agent = get_client_context(request)

    try:
        token_payload = decode_scoped_token(payload.totp_setup_token, "totp_setup")
    except Exception:
        return {
            "success": False,
            "message": "Session activation expirée. Les codes ne peuvent plus être envoyés.",
            "already_sent": False,
        }

    recovery_codes = [str(code or "").strip() for code in payload.recovery_codes or []]
    recovery_codes = [code for code in recovery_codes if code]

    if not recovery_codes:
        return {
            "success": False,
            "message": "Aucun code de secours disponible à envoyer.",
            "already_sent": False,
        }

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.id == token_payload.get("sub"))
        .filter(Utilisateur.date_suppression.is_(None))
        .first()
    )

    if not user:
        return {
            "success": False,
            "message": "Utilisateur introuvable.",
            "already_sent": False,
        }

    codes_digest = hashlib.sha256("|".join(recovery_codes).encode("utf-8")).hexdigest()

    previous_notifications = (
        db.query(NotificationSecurite.details)
        .filter(NotificationSecurite.utilisateur_id == user.id)
        .filter(NotificationSecurite.type_notification == "RECOVERY_CODES_SENT")
        .filter(NotificationSecurite.statut == "ENVOYE")
        .all()
    )

    already_sent = any(
        isinstance(details, dict)
        and details.get("activation_codes_digest") == codes_digest
        for (details,) in previous_notifications
    )

    if already_sent:
        return {
            "success": True,
            "already_sent": True,
            "message": "Les codes ont déjà été envoyés par email.",
        }

    sent = MailService().send_recovery_codes_email(
        to_email=user.email,
        recovery_codes=recovery_codes,
        db=db,
        utilisateur_id=user.id,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
        role=user.role,
        details={
            "source": "activation_totp",
            "activation_codes_digest": codes_digest,
        },
    )

    db.commit()

    return {
        "success": sent,
        "already_sent": False,
        "message": (
            "Les codes de secours ont été envoyés par email."
            if sent
            else "L’email n’a pas pu être envoyé. Veuillez réessayer."
        ),
    }
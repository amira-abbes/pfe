from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.constants import PERMISSION_LANCER_ELT
from app.core.security import decode_scoped_token
from app.db.database import get_db
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur
from app.schemas.webauthn import (
    WebAuthnSensitiveStartResponse,
    WebAuthnSensitiveVerifyRequest,
    WebAuthnSensitiveVerifyResponse,
)
from app.services.webauthn_service import WebAuthnService

router = APIRouter(prefix="/admin/sensitive", tags=["Admin - Actions sensibles"])


class LaunchEltRequest(BaseModel):
    sensitive_action_token: str


class LaunchEltResponse(BaseModel):
    success: bool
    code: str
    message: str


def get_webauthn_service(db: Session = Depends(get_db)) -> WebAuthnService:
    return WebAuthnService(db)


@router.post(
    "/elt/start-webauthn",
    response_model=WebAuthnSensitiveStartResponse,
)
def start_elt_webauthn(
    current_user: Utilisateur = Depends(require_permission(PERMISSION_LANCER_ELT)),
    service: WebAuthnService = Depends(get_webauthn_service),
):
    return service.start_sensitive_action(
        user=current_user,
        action_name="LAUNCH_ELT",
    )


@router.post(
    "/elt/verify-webauthn-demo",
    response_model=WebAuthnSensitiveVerifyResponse,
)
def verify_elt_webauthn_demo(
    payload: WebAuthnSensitiveVerifyRequest,
    current_user: Utilisateur = Depends(require_permission(PERMISSION_LANCER_ELT)),
    service: WebAuthnService = Depends(get_webauthn_service),
):
    return service.verify_sensitive_action_demo(
        user=current_user,
        webauthn_action_token=payload.webauthn_action_token,
    )


@router.post("/elt/launch", response_model=LaunchEltResponse)
def launch_elt(
    payload: LaunchEltRequest,
    current_user: Utilisateur = Depends(require_permission(PERMISSION_LANCER_ELT)),
    db: Session = Depends(get_db),
):
    try:
        token_payload = decode_scoped_token(
            payload.sensitive_action_token,
            "sensitive_action_confirmed",
        )
    except Exception:
        return {
            "success": False,
            "code": "SENSITIVE_ACTION_TOKEN_INVALID",
            "message": "Validation action sensible expirée ou invalide.",
        }

    if str(token_payload.get("sub")) != str(current_user.id):
        return {
            "success": False,
            "code": "SENSITIVE_ACTION_FORBIDDEN",
            "message": "Validation action sensible non autorisée.",
        }

    if token_payload.get("action") != "LAUNCH_ELT":
        return {
            "success": False,
            "code": "SENSITIVE_ACTION_INVALID",
            "message": "Action sensible invalide.",
        }

    db.add(
        JournalAudit(
            utilisateur_acteur_id=current_user.id,
            cible_utilisateur_id=current_user.id,
            action_effectuee="ADMIN_LAUNCH_ELT",
            niveau_risque="ELEVE",
            details={"source": "frontend_or_swagger"},
        )
    )
    db.commit()

    return {
        "success": True,
        "code": "ELT_LAUNCHED",
        "message": "Traitement ELT lancé avec succès.",
    }
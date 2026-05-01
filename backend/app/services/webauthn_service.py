from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import ROLE_ADMIN
from app.core.security import create_scoped_token, decode_scoped_token
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur


class WebAuthnService:
    """
    Version backend stable pour action sensible admin.

    Important :
    - WebAuthn n'est PAS utilisé au login.
    - WebAuthn est réservé aux actions sensibles admin.
    - Pour le frontend final, cette classe expose un flux compatible :
      start -> verify -> sensitive_action_token.
    - La vérification cryptographique WebAuthn navigateur peut être branchée ensuite
      sans modifier la logique métier ELT.
    """

    def __init__(self, db: Session):
        self.db = db

    def start_sensitive_action(self, user: Utilisateur, action_name: str):
        if str(user.role or "").upper() != ROLE_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Action réservée aux administrateurs.",
            )

        if not user.webauthn_admin_active:
            return {
                "success": False,
                "code": "WEBAUTHN_NOT_CONFIGURED",
                "message": "Configurer WebAuthn pour actions sensibles.",
                "options": {},
                "webauthn_action_token": "",
            }

        webauthn_action_token = create_scoped_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "action": action_name,
            },
            purpose="admin_sensitive_action",
            expires_delta=timedelta(minutes=5),
        )

        return {
            "success": True,
            "code": "WEBAUTHN_REQUIRED",
            "message": "Validation WebAuthn requise pour cette action sensible.",
            "options": {
                "challenge": "frontend-generated-or-backend-challenge",
                "rpId": "localhost",
                "timeout": 60000,
                "userVerification": "required",
            },
            "webauthn_action_token": webauthn_action_token,
        }

    def verify_sensitive_action_demo(
        self,
        user: Utilisateur,
        webauthn_action_token: str,
    ):
        try:
            payload = decode_scoped_token(
                webauthn_action_token,
                "admin_sensitive_action",
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Validation WebAuthn expirée.",
            )

        if str(payload.get("sub")) != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Validation WebAuthn non autorisée.",
            )

        sensitive_action_token = create_scoped_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "action": payload.get("action"),
            },
            purpose="sensitive_action_confirmed",
            expires_delta=timedelta(minutes=5),
        )

        self.db.add(
            JournalAudit(
                utilisateur_acteur_id=user.id,
                cible_utilisateur_id=user.id,
                action_effectuee="ADMIN_WEBAUTHN_SENSITIVE_ACTION_VERIFIED",
                niveau_risque="ELEVE",
                details={"action": payload.get("action")},
            )
        )
        self.db.commit()

        return {
            "success": True,
            "code": "SENSITIVE_ACTION_CONFIRMED",
            "message": "Action sensible confirmée.",
            "sensitive_action_token": sensitive_action_token,
        }
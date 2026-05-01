import pyotp
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    decrypt_secret,
    generate_numeric_code,
    hash_recovery_code,
    utc_now,
    verify_password,
)
from app.models.code_secours import CodeSecours
from app.models.identifiant_totp import IdentifiantTotp
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur
from app.services.mail_service import MailService


class AccountSecurityService:
    def __init__(self, db: Session):
        self.db = db
        self.mail_service = MailService()

    def get_recovery_codes_status(self, user: Utilisateur):
        total = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .count()
        )

        restants = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.est_utilise.is_(False))
            .count()
        )

        utilises = total - restants

        message = (
            "Codes de secours disponibles."
            if restants > 0
            else "Aucun code de secours disponible. Veuillez régénérer de nouveaux codes après confirmation TOTP."
        )

        return {
            "success": True,
            "total_codes": total,
            "codes_restants": restants,
            "codes_utilises": utilises,
            "message": message,
        }

    def regenerate_recovery_codes(
        self,
        user: Utilisateur,
        mot_de_passe: str,
        code_totp: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        if not verify_password(mot_de_passe, user.mot_de_passe_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mot de passe incorrect.",
            )

        totp_identity = (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user.id)
            .filter(IdentifiantTotp.est_actif.is_(True))
            .first()
        )

        if not totp_identity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authenticator non configuré.",
            )

        secret = decrypt_secret(totp_identity.secret_chiffre)

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configuration Authenticator invalide.",
            )

        clean_code = str(code_totp or "").strip().replace(" ", "")

        if not pyotp.TOTP(secret).verify(clean_code, valid_window=1):
            self._audit(
                user=user,
                action="RECOVERY_CODES_REGENERATE_TOTP_FAILED",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="MOYEN",
            )
            self.db.commit()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code Authenticator invalide.",
            )

        self.db.query(CodeSecours).filter(
            CodeSecours.utilisateur_id == user.id
        ).delete(synchronize_session=False)

        raw_codes: list[str] = []

        for _ in range(10):
            code = generate_numeric_code(10)
            raw_codes.append(code)

            self.db.add(
                CodeSecours(
                    utilisateur_id=user.id,
                    code_hash=hash_recovery_code(code),
                    est_utilise=False,
                    utilise_a=None,
                )
            )

        self._audit(
            user=user,
            action="SECURITY_RECOVERY_CODES_REGENERATED",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"count": 10},
        )

        self.mail_service.send_security_alert_email(
            to_email=user.email,
            subject="Codes de secours régénérés",
            message=(
                "Vos codes de secours ont été régénérés. "
                "Si vous n'êtes pas à l'origine de cette action, contactez immédiatement l'administrateur."
            ),
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "RECOVERY_CODES_REGENERATED"},
        )

        self.db.commit()

        return {
            "success": True,
            "code": "RECOVERY_CODES_REGENERATED",
            "message": "Nouveaux codes de secours générés. Ils ne seront affichés qu’une seule fois.",
            "recovery_codes": raw_codes,
        }

    def send_recovery_codes_by_email(
        self,
        user: Utilisateur,
        recovery_codes: list[str],
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        if not recovery_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucun code à envoyer.",
            )

        sent = self.mail_service.send_recovery_codes_email(
            to_email=user.email,
            recovery_codes=recovery_codes,
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self._audit(
            user=user,
            action="RECOVERY_CODES_SENT_BY_EMAIL",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"count": len(recovery_codes)},
        )

        self.db.commit()

        return {
            "success": sent,
            "message": (
                "Les codes de secours ont été envoyés par email."
                if sent
                else "Échec d’envoi des codes de secours par email."
            ),
        }

    def _audit(
        self,
        user: Utilisateur,
        action: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        niveau_risque: str = "FAIBLE",
        details: dict | None = None,
    ):
        self.db.add(
            JournalAudit(
                utilisateur_acteur_id=user.id,
                cible_utilisateur_id=user.id,
                action_effectuee=action,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=niveau_risque,
                details=details or {},
                date_action=utc_now(),
            )
        )
        self.db.flush()
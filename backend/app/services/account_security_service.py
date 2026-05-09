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
from app.models.tentative_connexion import TentativeConnexion
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

    def get_user_activity(self, user: Utilisateur, limit: int = 10):
        # 1. Fetch audits (excluding noisy session updates)
        audits = (
            self.db.query(JournalAudit)
            .filter(JournalAudit.cible_utilisateur_id == user.id)
            .filter(JournalAudit.action_effectuee != "SESSION_ACTIVITY_UPDATED")
            .order_by(JournalAudit.date_action.desc())
            .limit(limit)
            .all()
        )

        # 2. Fetch login attempts
        attempts = (
            self.db.query(TentativeConnexion)
            .filter(TentativeConnexion.utilisateur_id == user.id)
            .order_by(TentativeConnexion.date_tentative.desc())
            .limit(limit)
            .all()
        )

        merged_activity = []

        # Process audits
        for a in audits:
            action = a.action_effectuee
            description = action.replace("_", " ").capitalize()
            status = "info"

            # Detailed mapping
            if action in ["LOGIN_SUCCESS", "ADMIN_LOGIN_SUCCESS"]:
                description = "Connexion réussie"
                status = "success"
            elif action in ["USER_LOGOUT", "ADMIN_LOGOUT"]:
                description = "Déconnexion"
                status = "info"
            elif action == "LOGIN_RECOVERY_CODE_SUCCESS":
                description = "Code de secours utilisé"
                status = "info"
            elif action == "SECURITY_RECOVERY_CODES_REGENERATED":
                description = "Codes de secours régénérés"
                status = "info"
            elif action == "SESSION_CREATED":
                description = "Nouvelle session créée"
                status = "info"
            elif "FAILURE" in action or "FAILED" in action or "BLOCKED" in action:
                status = "error"
                if "TOTP" in action:
                    description = "Échec vérification Authenticator"
                elif "RECOVERY" in action:
                    description = "Échec code de secours"
                elif "PASSWORD" in action:
                    description = "Échec mot de passe"
                elif "LOCKOUT" in action:
                    description = "Compte temporairement bloqué"

            merged_activity.append({
                "id": f"audit_{a.id}",
                "type": action,
                "description": description,
                "date": a.date_action,
                "adresse_ip": a.adresse_ip,
                "user_agent": a.user_agent,
                "status": status,
                "details": a.details
            })

        # Process attempts (only failures, successes are already in audits)
        for t in attempts:
            if not t.succes:
                # Check if we already have a similar error audit at the same time
                exists = any(
                    abs((m["date"] - t.date_tentative).total_seconds()) < 2
                    for m in merged_activity if m["status"] == "error"
                )
                if not exists:
                    description = "Tentative de connexion échouée"
                    if t.raison_echec == "INVALID_CREDENTIALS":
                        description += " (Identifiants invalides)"
                    
                    merged_activity.append({
                        "id": f"attempt_{t.id}",
                        "type": "LOGIN_FAILED",
                        "description": description,
                        "date": t.date_tentative,
                        "adresse_ip": t.adresse_ip,
                        "user_agent": t.user_agent,
                        "status": "error",
                        "details": t.details
                    })

        # Sort merged list by date and limit
        merged_activity.sort(key=lambda x: x["date"], reverse=True)
        
        return {
            "success": True,
            "activities": merged_activity[:limit]
        }
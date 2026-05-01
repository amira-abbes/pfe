from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import SESSION_REVOKED
from app.core.security import decode_scoped_token, ensure_aware_utc, hash_token, utc_now
from app.models.jeton_reinitialisation import JetonReinitialisationMotDePasse
from app.models.journal_audit import JournalAudit
from app.models.notification_securite import NotificationSecurite
from app.models.session_utilisateur import SessionUtilisateur
from app.models.utilisateur import Utilisateur


class SecurityIncidentService:
    def __init__(self, db: Session):
        self.db = db

    def report_suspicious_activity(
        self,
        report_token: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        try:
            try:
                payload = decode_scoped_token(
                    report_token,
                    "security_incident_report",
                )
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce lien de signalement est invalide ou expiré.",
                )

            try:
                user_uuid = UUID(str(payload.get("sub")))
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce lien de signalement est invalide ou expiré.",
                )

            email = payload.get("email")
            incident_id = payload.get("incident_id")
            source_ip = payload.get("source_ip")
            source_user_agent = payload.get("source_user_agent")
            detected_at = payload.get("detected_at")

            user = (
                self.db.query(Utilisateur)
                .filter(Utilisateur.id == user_uuid)
                .filter(Utilisateur.date_suppression.is_(None))
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Utilisateur introuvable.",
                )

            if self._is_already_reported(
                user_id=user.id,
                incident_id=incident_id,
                source_ip=source_ip,
                detected_at=detected_at,
            ):
                return {
                    "success": True,
                    "code": "SECURITY_INCIDENT_ALREADY_REPORTED",
                    "status": "already_reported",
                    "message": "Signalement déjà enregistré. Aucune action supplémentaire n’est nécessaire.",
                }

            now = utc_now()

            revoked_count = self._revoke_active_sessions(
                user_id=user.id,
                revoked_at=now,
                reason="Incident de sécurité signalé par utilisateur",
            )

            user.date_derniere_alerte_securite = now
            user.date_modification = now
            self.db.add(user)

            incident_details = {
                "email": email or user.email,
                "incident_id": incident_id,
                "reported_from_ip": adresse_ip,
                "reported_from_user_agent": user_agent,
                "original_attempt_ip": source_ip,
                "original_attempt_user_agent": source_user_agent,
                "original_detected_at": detected_at,
                "sessions_revoked": revoked_count,
                "reinforced_monitoring": True,
            }

            self._audit(
                user=user,
                action="SECURITY_INCIDENT_REPORTED",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=incident_details,
            )
            self._create_security_notification(
                user=user,
                type_notification="SECURITY_INCIDENT_REPORTED",
                subject="Signalement d’activité suspecte",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=incident_details,
            )

            self.db.commit()

            return {
                "success": True,
                "code": "SECURITY_INCIDENT_REPORTED",
                "status": "success",
                "message": "Signalement enregistré. Vos sessions actives ont été révoquées.",
                "force_relogin": True,
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            print("ERREUR SECURITY_INCIDENT_REPORTED:", repr(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur interne pendant l’enregistrement du signalement.",
            )

    def confirm_admin_security_report(
        self,
        report_token: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        try:
            token_row = self._get_security_report_token(report_token)
            now = utc_now()

            if not token_row:
                return self._report_response("invalid")
            if self._is_expired(token_row, now):
                return self._report_response("expired")

            user = self._get_report_user(token_row)
            if not user:
                return self._report_response("invalid")

            if token_row.utilise_a is not None:
                self._audit(
                    user=user,
                    action="SECURITY_REPORT_ALREADY_CONFIRMED",
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    details=token_row.details or {},
                )
                self.db.commit()
                return self._report_response("already_reported", success=True)

            token_row.utilise_a = now
            self.db.add(token_row)

            revoked_count = self._revoke_active_sessions(
                user_id=user.id,
                revoked_at=now,
                reason="Signalement activité suspecte",
            )

            details = {
                **(token_row.details or {}),
                "reported_from_ip": adresse_ip,
                "reported_from_user_agent": user_agent,
                "sessions_revoked": revoked_count,
                "force_relogin": True,
            }

            self._audit(
                user=user,
                action="SECURITY_REPORT_CONFIRMED",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=details,
            )
            self._create_security_notification(
                user=user,
                type_notification="SECURITY_REPORT_CONFIRMED",
                subject="Signalement activité suspecte",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=details,
            )

            self.db.commit()

            return {
                "success": True,
                "code": "SECURITY_REPORT_CONFIRMED",
                "status": "success",
                "message": "Signalement enregistré. Vos sessions actives ont été révoquées.",
                "force_relogin": True,
            }
        except Exception as exc:
            self.db.rollback()
            print("ERREUR SECURITY_REPORT_CONFIRMED:", repr(exc))
            return {
                "success": False,
                "code": "SECURITY_REPORT_ERROR",
                "status": "error",
                "message": "Le signalement n’a pas pu être enregistré correctement.",
            }

    def get_admin_security_report_status(self, report_token: str):
        token_row = self._get_security_report_token(report_token)
        now = utc_now()

        if not token_row:
            return self._report_response("invalid")
        if self._is_expired(token_row, now):
            return self._report_response("expired")
        if not self._get_report_user(token_row):
            return self._report_response("invalid")
        if token_row.utilise_a is not None:
            return self._report_response("already_reported", success=True)

        return {
            "success": True,
            "code": "SECURITY_REPORT_PENDING_CONFIRMATION",
            "status": "pending_confirmation",
            "message": "Signalement en attente de confirmation.",
            "remaining_seconds": self._remaining_seconds(token_row.expire_a),
        }

    def _get_security_report_token(self, report_token: str):
        return (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(report_token))
            .filter(JetonReinitialisationMotDePasse.type_jeton == "SECURITY_REPORT")
            .first()
        )

    def _get_report_user(self, token_row):
        return (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == token_row.utilisateur_id)
            .filter(Utilisateur.est_actif.is_(True))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

    def _is_expired(self, token_row, now) -> bool:
        expire_a = ensure_aware_utc(token_row.expire_a)
        return bool(expire_a and expire_a <= now)

    def _remaining_seconds(self, until_value) -> int:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return 0
        return max(0, int((until_value - utc_now()).total_seconds()))

    def _revoke_active_sessions(self, user_id, revoked_at, reason: str) -> int:
        return self.db.query(SessionUtilisateur).filter(
            SessionUtilisateur.utilisateur_id == user_id,
            SessionUtilisateur.revoque_a.is_(None),
        ).update(
            {
                "revoque_a": revoked_at,
                "raison_revocation": reason,
                "statut_session": SESSION_REVOKED,
            },
            synchronize_session=False,
        )

    def _audit(
        self,
        user: Utilisateur,
        action: str,
        adresse_ip: str | None,
        user_agent: str | None,
        details: dict,
    ) -> None:
        self.db.add(
            JournalAudit(
                utilisateur_acteur_id=user.id,
                cible_utilisateur_id=user.id,
                action_effectuee=action,
                niveau_risque="ELEVE",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=details,
            )
        )
        self.db.flush()

    def _create_security_notification(
        self,
        user: Utilisateur,
        type_notification: str,
        subject: str,
        adresse_ip: str | None,
        user_agent: str | None,
        details: dict,
    ) -> None:
        self.db.add(
            NotificationSecurite(
                utilisateur_id=user.id,
                type_notification=type_notification,
                email_destinataire=user.email,
                sujet=subject,
                statut="ENVOYE",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=details,
                date_envoi=utc_now(),
            )
        )
        self.db.flush()

    def _report_response(self, status_value: str, success: bool = False):
        responses = {
            "invalid": {
                "success": False,
                "code": "SECURITY_REPORT_INVALID",
                "status": "invalid",
                "message": "Ce lien de signalement est invalide.",
            },
            "expired": {
                "success": False,
                "code": "SECURITY_REPORT_EXPIRED",
                "status": "expired",
                "message": "Ce lien de signalement n’est plus valide.",
            },
            "already_reported": {
                "success": success,
                "code": "SECURITY_REPORT_ALREADY_CONFIRMED",
                "status": "already_reported",
                "message": "Signalement déjà enregistré. Aucune action supplémentaire n’est nécessaire.",
            },
        }
        return responses[status_value]

    def _is_already_reported(
        self,
        user_id,
        incident_id: str | None,
        source_ip: str | None,
        detected_at: str | None,
    ) -> bool:
        query = self.db.query(JournalAudit).filter(
            JournalAudit.cible_utilisateur_id == user_id,
            JournalAudit.action_effectuee == "SECURITY_INCIDENT_REPORTED",
        )

        if incident_id:
            return (
                query.filter(JournalAudit.details["incident_id"].astext == incident_id)
                .first()
                is not None
            )

        if source_ip and detected_at:
            return (
                query.filter(JournalAudit.details["original_attempt_ip"].astext == source_ip)
                .filter(JournalAudit.details["original_detected_at"].astext == detected_at)
                .first()
                is not None
            )

        return False

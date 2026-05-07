from datetime import timedelta
from urllib.parse import quote

import pyotp
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.constants import (
    AUDIT_PASSWORD_RESET_FROM_LOCKOUT_LINK_INVALID,
    AUDIT_PASSWORD_RESET_FROM_LOCKOUT_RECOVERY_CODE_FAILED,
    AUDIT_PASSWORD_RESET_FROM_LOCKOUT_SUCCESS,
    AUDIT_PASSWORD_RESET_FROM_LOCKOUT_TOTP_FAILED,
    AUDIT_PASSWORD_RESET_LINK_INVALID,
    AUDIT_PASSWORD_RESET_RECOVERY_CODE_FAILED,
    AUDIT_PASSWORD_RESET_REQUEST,
    AUDIT_PASSWORD_RESET_REQUEST_UNKNOWN_EMAIL,
    AUDIT_PASSWORD_RESET_SUCCESS,
    AUDIT_PASSWORD_RESET_TOTP_FAILED,
    SESSION_REVOKED,
    TOKEN_PASSWORD_RESET,
    TOKEN_PASSWORD_RESET_FROM_LOCKOUT,
)
from app.core.security import (
    create_scoped_token,
    decode_scoped_token,
    decrypt_secret,
    ensure_aware_utc,
    generate_raw_password_reset_token,
    hash_password,
    hash_recovery_code,
    hash_token,
    utc_now,
)
from app.models.code_secours import CodeSecours
from app.models.identifiant_totp import IdentifiantTotp
from app.models.jeton_reinitialisation import JetonReinitialisationMotDePasse
from app.models.journal_audit import JournalAudit
from app.models.session_utilisateur import SessionUtilisateur
from app.models.utilisateur import Utilisateur
from app.services.mail_service import MailService
from app.services.password_policy_service import PasswordPolicyService


class PasswordResetService:
    GENERIC_MESSAGE = (
        "Si un compte existe avec cet email, un lien de réinitialisation a été envoyé."
    )

    RESET_MFA_COOLDOWN_SECONDS = 30
    RESET_RECOVERY_MAX_FAILURES = 5
    RESET_RECOVERY_LOCK_SECONDS = 300

    def __init__(self, db: Session):
        self.db = db
        self.mail_service = MailService()
        self.password_policy = PasswordPolicyService()

    def request_reset(
        self,
        email: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        email_clean = str(email or "").strip().lower()

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.email == email_clean)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

        if not user or not user.est_actif:
            self._audit(
                action=AUDIT_PASSWORD_RESET_REQUEST_UNKNOWN_EMAIL,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="MOYEN",
                details={"email": email_clean},
            )
            self.db.commit()

            return {
                "success": True,
                "code": "PASSWORD_RESET_REQUEST_ACCEPTED",
                "message": self.GENERIC_MESSAGE,
                "reset_link_debug": None,
            }

        raw_token = generate_raw_password_reset_token()

        reset_token = JetonReinitialisationMotDePasse(
            utilisateur_id=user.id,
            jeton_hash=hash_token(raw_token),
            type_jeton=TOKEN_PASSWORD_RESET,
            type_token=TOKEN_PASSWORD_RESET,
            expire_a=utc_now()
            + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self.db.add(reset_token)
        self.db.flush()

        reset_link = f"{settings.FRONTEND_BASE_URL}/password-reset?token={raw_token}"

        self._audit(
            action=AUDIT_PASSWORD_RESET_REQUEST,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
        )

        self.mail_service.send_password_reset_email(
            to_email=user.email,
            reset_link=reset_link,
            expire_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            from_lockout=False,
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self.db.commit()

        return {
            "success": True,
            "code": "PASSWORD_RESET_REQUEST_ACCEPTED",
            "message": self.GENERIC_MESSAGE,
            "reset_link_debug": reset_link if settings.MAIL_DEBUG_MODE else None,
        }

    def verify_token(
        self,
        token: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        reset_token = self._get_reset_token(token)

        if not reset_token or not reset_token.utilisateur:
            self._audit_invalid_link(
                user_id=None,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                reason="token_not_found",
                type_jeton=None,
            )
            self.db.commit()
            return self._invalid_response()

        user = reset_token.utilisateur
        invalid_reason = self._invalid_reason(reset_token)

        if invalid_reason:
            self._audit_invalid_link(
                user_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                reason=invalid_reason,
                type_jeton=reset_token.type_jeton,
            )
            self.db.commit()
            return self._invalid_response()

        reset_mfa_token = create_scoped_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "reset_token_hash": reset_token.jeton_hash,
                "type_jeton": reset_token.type_jeton,
            },
            purpose="password_reset_mfa",
            expires_delta=timedelta(minutes=settings.MFA_PENDING_EXPIRE_MINUTES),
        )

        return {
            "success": True,
            "code": "PASSWORD_RESET_TOKEN_VALID",
            "message": "Veuillez confirmer votre identité pour continuer.",
            "email": user.email,
            "role": str(user.role or "").upper(),
            "reset_mfa_token": reset_mfa_token,
            "requires_mfa": True,
        }

    def verify_totp(
        self,
        reset_mfa_token: str,
        code: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        user, reset_token, type_jeton = self._decode_reset_mfa(reset_mfa_token)

        if reset_token.mfa_totp_bloque:
            return self._recovery_required_response()

        cooldown_remaining = self._remaining_seconds(reset_token.mfa_cooldown_jusqu_a)
        if cooldown_remaining > 0:
            return self._cooldown_response(cooldown_remaining)
        if reset_token.mfa_cooldown_jusqu_a is not None:
            reset_token.mfa_cooldown_jusqu_a = None
            self.db.add(reset_token)
            self.db.flush()

        totp = (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user.id)
            .filter(IdentifiantTotp.est_actif.is_(True))
            .first()
        )

        if not totp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOTP non configuré.",
            )

        secret = decrypt_secret(totp.secret_chiffre)

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Secret TOTP invalide.",
            )

        cleaned_code = str(code or "").strip().replace(" ", "")
        if len(cleaned_code) != 6 or not cleaned_code.isdigit():
            return {
                "success": False,
                "code": "MFA_INVALID_FORMAT",
                "status": "invalid_format",
                "message": "Le code doit contenir 6 chiffres.",
                "reset_password_token": None,
                "temps_restant": None,
            }

        valid = pyotp.TOTP(secret).verify(cleaned_code, valid_window=1)

        if not valid:
            action = (
                AUDIT_PASSWORD_RESET_FROM_LOCKOUT_TOTP_FAILED
                if type_jeton == TOKEN_PASSWORD_RESET_FROM_LOCKOUT
                else AUDIT_PASSWORD_RESET_TOTP_FAILED
            )
            return self._handle_reset_totp_failure(
                user=user,
                reset_token=reset_token,
                action=action,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        self._reset_mfa_state(reset_token)
        self.db.add(reset_token)
        self.db.commit()

        reset_password_token = self._issue_reset_password_token(user, reset_token)

        return {
            "success": True,
            "code": "MFA_VERIFIED",
            "status": "success",
            "message": "Identité vérifiée. Vous pouvez définir un nouveau mot de passe.",
            "reset_password_token": reset_password_token,
            "temps_restant": None,
        }
    def verify_recovery_code(
        self,
        reset_mfa_token: str,
        code_secours: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        user, reset_token, type_jeton = self._decode_reset_mfa(reset_mfa_token)

        recovery_remaining = self._remaining_seconds(
            reset_token.mfa_recovery_bloque_jusqu_a
        )
        if recovery_remaining > 0:
            return {
                "success": False,
                "code": "RECOVERY_CODE_COOLDOWN",
                "status": "cooldown",
                "reason": "recovery_code_cooldown",
                "message": "Trop de codes de secours invalides. Veuillez patienter avant de réessayer.",
                "reset_password_token": None,
                "temps_restant": self._format_seconds(recovery_remaining),
                "remaining_seconds": recovery_remaining,
            }
        if reset_token.mfa_recovery_bloque_jusqu_a is not None:
            reset_token.mfa_recovery_bloque_jusqu_a = None
            self.db.add(reset_token)
            self.db.flush()

        code_hash = hash_recovery_code(code_secours)

        recovery = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.code_hash == code_hash)
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > utc_now()))
            .first()
        )

        if not recovery:
            action = (
                AUDIT_PASSWORD_RESET_FROM_LOCKOUT_RECOVERY_CODE_FAILED
                if type_jeton == TOKEN_PASSWORD_RESET_FROM_LOCKOUT
                else AUDIT_PASSWORD_RESET_RECOVERY_CODE_FAILED
            )
            return self._handle_reset_recovery_failure(
                user=user,
                reset_token=reset_token,
                action=action,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        now = utc_now()

        recovery.utilise = True
        recovery.est_utilise = True
        recovery.utilise_a = now
        user.nombre_echecs_totp = 0
        user.blocage_totp_jusqu_a = None
        user.date_modification = now
        self._reset_mfa_state(reset_token)

        self.db.add(recovery)
        self.db.add(user)
        self.db.add(reset_token)

        self.mail_service.send_security_alert_email(
            to_email=user.email,
            subject="Code de secours utilisé",
            message="Un code de secours a été utilisé pour confirmer une réinitialisation de mot de passe.",
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "PASSWORD_RESET_RECOVERY_CODE"},
        )

        self.db.commit()

        reset_password_token = self._issue_reset_password_token(user, reset_token)

        return {
            "success": True,
            "code": "MFA_VERIFIED",
            "status": "success",
            "message": "Identité vérifiée. Vous pouvez définir un nouveau mot de passe.",
            "reset_password_token": reset_password_token,
            "temps_restant": None,
        }

    def verify_recovery_token(
        self,
        token: str,
        code_secours: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        reset_token = self._get_reset_token(token)
        if (
            not reset_token
            or reset_token.type_jeton != "RESET_PASSWORD_RECOVERY_CODE"
            or reset_token.utilise_a is not None
        ):
            return self._invalid_mfa_response()

        expire_a = ensure_aware_utc(reset_token.expire_a)
        if expire_a and expire_a <= utc_now():
            return self._invalid_mfa_response()

        user = reset_token.utilisateur
        role = str(user.role or "").upper() if user else ""
        if (
            not user
            or role not in {"USER", "ADMIN", "SUPER_ADMIN"}
            or not user.est_actif
            or user.date_suppression is not None
        ):
            return self._invalid_mfa_response()

        if self._remaining_seconds(reset_token.mfa_recovery_bloque_jusqu_a) > 0:
            remaining = self._remaining_seconds(reset_token.mfa_recovery_bloque_jusqu_a)
            return {
                "success": False,
                "code": "RECOVERY_CODE_COOLDOWN",
                "status": "cooldown",
                "reason": "recovery_code_cooldown",
                "message": "Trop de codes de secours invalides. Veuillez patienter avant de réessayer.",
                "reset_password_token": None,
                "temps_restant": self._format_seconds(remaining),
                "remaining_seconds": remaining,
            }
        if reset_token.mfa_recovery_bloque_jusqu_a is not None:
            reset_token.mfa_recovery_bloque_jusqu_a = None
            self.db.add(reset_token)
            self.db.flush()

        recovery = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.code_hash == hash_recovery_code(code_secours))
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > utc_now()))
            .first()
        )

        if not recovery:
            return self._handle_reset_recovery_failure(
                user=user,
                reset_token=reset_token,
                action=AUDIT_PASSWORD_RESET_FROM_LOCKOUT_RECOVERY_CODE_FAILED,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        now = utc_now()
        recovery.utilise = True
        recovery.est_utilise = True
        recovery.utilise_a = now
        self.db.add(recovery)
        self.db.add(reset_token)
        self.db.commit()

        reset_password_token = self._issue_reset_password_token(user, reset_token)
        return {
            "success": True,
            "code": "MFA_VERIFIED",
            "status": "success",
            "message": "Code de récupération validé. Vous pouvez définir un nouveau mot de passe.",
            "reset_password_token": reset_password_token,
            "temps_restant": None,
        }
    def complete_reset(
        self,
        reset_password_token: str,
        nouveau_mot_de_passe: str,
        confirmation_mot_de_passe: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        try:
            payload = decode_scoped_token(
                reset_password_token,
                "password_reset_complete",
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session de réinitialisation expirée.",
            )

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == payload.get("sub"))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable.",
            )

        reset_token = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == payload.get("reset_token_hash"))
            .first()
        )

        if not reset_token or reset_token.utilise_a is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lien de réinitialisation invalide ou expiré.",
            )

        expire_a = ensure_aware_utc(reset_token.expire_a)
        if expire_a and expire_a <= utc_now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lien de réinitialisation invalide ou expiré.",
            )

        try:
            self.password_policy.validate(
                password=nouveau_mot_de_passe,
                confirm_password=confirmation_mot_de_passe,
                email=user.email,
                nom_complet=user.nom_complet,
                old_password_hash=user.mot_de_passe_hash,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )

        now = utc_now()

        user.mot_de_passe_hash = hash_password(nouveau_mot_de_passe)
        user.nombre_echecs_password = 0
        user.nombre_echecs_totp = 0
        user.blocage_password_jusqu_a = None
        user.blocage_totp_jusqu_a = None
        user.password_lockout_resolved_at = now
        user.password_lockout_requires_mail_action = False
        user.password_lockout_mail_sent_at = None
        user.password_lockout_mail_expires_at = None
        user.date_dernier_changement_mot_de_passe = now
        user.date_modification = now

        reset_token.utilise_a = now

        self.db.query(SessionUtilisateur).filter(
            SessionUtilisateur.utilisateur_id == user.id,
            SessionUtilisateur.revoque_a.is_(None),
        ).update(
            {
                "statut_session": SESSION_REVOKED,
                "revoque_a": now,
                "raison_revocation": "Réinitialisation mot de passe",
            },
            synchronize_session=False,
        )

        self.db.add(user)
        self.db.add(reset_token)

        action = (
            AUDIT_PASSWORD_RESET_FROM_LOCKOUT_SUCCESS
            if reset_token.type_jeton == TOKEN_PASSWORD_RESET_FROM_LOCKOUT
            else AUDIT_PASSWORD_RESET_SUCCESS
        )

        self._audit(
            action=action,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
        )

        self.mail_service.send_password_changed_email(
            to_email=user.email,
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self.db.commit()

        return {
            "success": True,
            "code": "PASSWORD_RESET_SUCCESS",
            "message": "Votre mot de passe a été modifié avec succès.",
            "redirect_to": "/login",
        }

    def _handle_reset_mfa_failure(
        self,
        user: Utilisateur,
        action: str,
        type_tentative: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        current = int(user.nombre_echecs_totp or 0)
        new_count = current + 1

        delay_seconds = 0
        lock_minutes = 0
        risk = "MOYEN"

        is_admin = str(user.role or "").upper() == "ADMIN"

        if is_admin:
            if new_count <= 2:
                pass
            elif new_count == 3:
                delay_seconds = 30
            elif new_count == 4:
                delay_seconds = 60
            elif new_count == 5:
                lock_minutes = 10
                risk = "ELEVE"
            else:
                lock_minutes = 15
                risk = "CRITIQUE"
        else:
            if new_count <= 3:
                pass
            elif new_count == 4:
                delay_seconds = 30
            elif new_count == 5:
                delay_seconds = 60
            else:
                lock_minutes = 5
                risk = "ELEVE"

        user.nombre_echecs_totp = new_count
        user.date_modification = now

        if lock_minutes > 0:
            user.blocage_totp_jusqu_a = now + timedelta(minutes=lock_minutes)
        elif delay_seconds > 0:
            user.blocage_totp_jusqu_a = now + timedelta(seconds=delay_seconds)

        self.db.add(user)

        self._audit(
            action=action,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque=risk,
            details={"attempt": new_count, "type": type_tentative},
        )

        if lock_minutes > 0:
            self.mail_service.send_security_alert_email(
                to_email=user.email,
                subject="Blocage temporaire MFA",
                message="Plusieurs tentatives MFA échouées ont été détectées pendant une réinitialisation de mot de passe.",
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"attempt": new_count, "type": type_tentative},
            )
            self.db.commit()

            return {
                "success": False,
                "code": "MFA_TEMPORARILY_LOCKED",
                "message": f"La vérification en deux étapes est temporairement bloquée pendant {lock_minutes} minutes.",
                "reset_password_token": None,
                "temps_restant": f"{lock_minutes:02d}:00",
            }

        if delay_seconds > 0:
            self.db.commit()

            return {
                "success": False,
                "code": "MFA_DELAY_REQUIRED",
                "message": f"Plusieurs erreurs MFA. Veuillez réessayer dans {delay_seconds} secondes.",
                "reset_password_token": None,
                "temps_restant": f"00:{delay_seconds:02d}" if delay_seconds < 60 else "01:00",
            }

        self.db.commit()

        return {
            "success": False,
            "code": "MFA_INVALID",
            "message": "Code invalide.",
            "reset_password_token": None,
            "temps_restant": None,
        }

    def _handle_reset_totp_failure(
        self,
        user: Utilisateur,
        reset_token,
        action: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        new_count = int(reset_token.mfa_echecs_totp or 0) + 1

        reset_token.mfa_echecs_totp = new_count
        reset_token.mfa_dernier_echec_a = now

        self._audit(
            action=action,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN" if new_count < 4 else "ELEVE",
            details={"attempt": new_count, "type": "PASSWORD_RESET_TOTP"},
        )

        if new_count <= 2 or new_count == 4:
            self.db.add(reset_token)
            self.db.commit()
            return {
                "success": False,
                "code": "MFA_INVALID",
                "status": "invalid_code",
                "message": "Code incorrect. Veuillez réessayer.",
                "reset_password_token": None,
                "temps_restant": None,
            }

        if new_count == 3:
            reset_token.mfa_cooldown_jusqu_a = now + timedelta(
                seconds=self.RESET_MFA_COOLDOWN_SECONDS
            )
            self.db.add(reset_token)
            self.db.commit()
            return self._cooldown_response(self.RESET_MFA_COOLDOWN_SECONDS)

        reset_token.mfa_totp_bloque = True
        reset_token.mfa_cooldown_jusqu_a = None
        self.db.add(reset_token)

        raw_recovery_token = generate_raw_password_reset_token()
        recovery_token = JetonReinitialisationMotDePasse(
            utilisateur_id=user.id,
            jeton_hash=hash_token(raw_recovery_token),
            type_jeton="RESET_PASSWORD_RECOVERY_CODE",
            type_token="RESET_PASSWORD_RECOVERY_CODE",
            expire_a=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"source": "password_reset_from_lockout_mfa_blocked"},
        )
        self.db.add(recovery_token)
        self.db.flush()
        recovery_link = (
            f"{settings.FRONTEND_BASE_URL}/recovery-code/verify"
            f"?token={quote(raw_recovery_token, safe='')}"
        )

        mail_sent = self.mail_service.send_admin_reset_password_mfa_recovery_email(
            to_email=user.email,
            recovery_link=recovery_link,
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "PASSWORD_RESET_MFA_BLOCKED", "attempt": new_count},
        )

        self.db.commit()
        response = self._recovery_required_response()
        response["mail_sent"] = bool(mail_sent)
        return response

    def _handle_reset_recovery_failure(
        self,
        user: Utilisateur,
        reset_token,
        action: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        new_count = int(reset_token.mfa_echecs_recovery or 0) + 1
        reset_token.mfa_echecs_recovery = new_count
        reset_token.mfa_dernier_echec_a = now

        self._audit(
            action=action,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"attempt": new_count, "type": "PASSWORD_RESET_RECOVERY_CODE"},
        )
        self.db.add(reset_token)

        from app.services.auth_service import AuthService

        user.recovery_code_failed_attempts = max(new_count - 1, 0)
        response = AuthService(self.db)._handle_recovery_code_failure(
            user=user,
            role=str(user.role or "").upper(),
            after_mfa_blocked=True,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        remaining = response.get("remaining_seconds")
        reset_token.mfa_recovery_bloque_jusqu_a = (
            now + timedelta(seconds=int(remaining))
            if remaining and response.get("status") in {"cooldown", "recovery_alert_sent"}
            else None
        )
        self.db.add(reset_token)
        self.db.commit()
        response["reset_password_token"] = None
        response["temps_restant"] = self._format_seconds(remaining) if remaining else None
        return response

    def _cooldown_response(self, remaining_seconds: int):
        return {
            "success": False,
            "code": "MFA_DELAY_REQUIRED",
            "status": "cooldown",
            "message": f"Plusieurs erreurs MFA. Veuillez réessayer dans {remaining_seconds} secondes.",
            "reset_password_token": None,
            "temps_restant": self._format_seconds(remaining_seconds),
            "cooldown_seconds": remaining_seconds,
            "remaining_seconds": remaining_seconds,
        }

    def _recovery_required_response(self):
        return {
            "success": False,
            "code": "MFA_RECOVERY_REQUIRED",
            "status": "recovery_required",
            "message": "Vérification MFA bloquée temporairement. Un email de sécurité vous a été envoyé.",
            "reset_password_token": None,
            "temps_restant": None,
            "recovery_method": "backup_code",
        }

    def _reset_mfa_state(self, reset_token) -> None:
        reset_token.mfa_echecs_totp = 0
        reset_token.mfa_dernier_echec_a = None
        reset_token.mfa_cooldown_jusqu_a = None
        reset_token.mfa_totp_bloque = False
        reset_token.mfa_echecs_recovery = 0
        reset_token.mfa_recovery_bloque_jusqu_a = None

    def _remaining_seconds(self, until_value) -> int:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return 0
        return max(0, int((until_value - utc_now()).total_seconds()))

    def _format_seconds(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _issue_reset_password_token(self, user: Utilisateur, reset_token) -> str:
        return create_scoped_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "reset_token_hash": reset_token.jeton_hash,
                "type_jeton": reset_token.type_jeton,
            },
            purpose="password_reset_complete",
            expires_delta=timedelta(minutes=10),
        )

    def _decode_reset_mfa(self, reset_mfa_token: str):
        try:
            payload = decode_scoped_token(reset_mfa_token, "password_reset_mfa")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session MFA expirée.",
            )

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == payload.get("sub"))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable.",
            )

        reset_token = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == payload.get("reset_token_hash"))
            .first()
        )

        if not reset_token or reset_token.utilise_a is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lien de réinitialisation invalide ou expiré.",
            )

        expire_a = ensure_aware_utc(reset_token.expire_a)
        if expire_a and expire_a <= utc_now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lien de réinitialisation invalide ou expiré.",
            )

        return user, reset_token, reset_token.type_jeton

    def _get_reset_token(self, raw_token: str):
        return (
            self.db.query(JetonReinitialisationMotDePasse)
            .options(selectinload(JetonReinitialisationMotDePasse.utilisateur))
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(raw_token))
            .first()
        )

    def _invalid_reason(self, reset_token):
        if reset_token.utilise_a is not None:
            return "token_already_used"

        expire_a = ensure_aware_utc(reset_token.expire_a)
        if expire_a and expire_a <= utc_now():
            return "token_expired"

        return None

    def _invalid_response(self):
        return {
            "success": False,
            "code": "PASSWORD_RESET_LINK_INVALID",
            "message": "Lien de réinitialisation invalide ou expiré.",
            "email": None,
            "reset_mfa_token": None,
            "requires_mfa": False,
        }

    def _invalid_mfa_response(self):
        return {
            "success": False,
            "code": "PASSWORD_RESET_LINK_INVALID",
            "status": "invalid_or_expired_token",
            "message": "Lien invalide ou expiré. Veuillez recommencer la procédure depuis la page de connexion.",
            "reset_password_token": None,
            "temps_restant": None,
        }

    def _audit_invalid_link(
        self,
        user_id,
        adresse_ip: str | None,
        user_agent: str | None,
        reason: str,
        type_jeton: str | None = None,
    ):
        action = (
            AUDIT_PASSWORD_RESET_FROM_LOCKOUT_LINK_INVALID
            if type_jeton == TOKEN_PASSWORD_RESET_FROM_LOCKOUT
            else AUDIT_PASSWORD_RESET_LINK_INVALID
        )

        self._audit(
            action=action,
            cible_id=user_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"reason": reason},
        )

    def _is_locked(self, until_value) -> bool:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return False
        return until_value > utc_now()

    def _format_remaining(self, until_value) -> str:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return "00:00"

        seconds = max(0, int((until_value - utc_now()).total_seconds()))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _audit(
        self,
        action: str,
        acteur_id=None,
        cible_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        niveau_risque: str = "FAIBLE",
        details: dict | None = None,
    ):
        self.db.add(
            JournalAudit(
                utilisateur_acteur_id=acteur_id,
                cible_utilisateur_id=cible_id,
                action_effectuee=action,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=niveau_risque,
                details=details or {},
            )
        )
        self.db.flush()




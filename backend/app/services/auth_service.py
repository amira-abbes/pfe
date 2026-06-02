import base64
from datetime import timedelta
from io import BytesIO
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

import pyotp
import qrcode
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    AUDIT_ADMIN_LOGIN_PASSWORD_FAILED,
    AUDIT_ADMIN_LOGIN_SUCCESS,
    AUDIT_ADMIN_LOGIN_TOTP_FAILED,
    AUDIT_ADMIN_PASSWORD_VALID_MFA_PENDING,
    AUDIT_LOGIN_PASSWORD_FAILED,
    AUDIT_LOGIN_SUCCESS,
    AUDIT_LOGIN_TOTP_FAILED,
    AUDIT_PASSWORD_VALID_MFA_PENDING,
    AUDIT_SESSION_CREATED,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    SESSION_ACTIVE,
    SESSION_REVOKED,
    STATUT_ACTIVE,
    STATUT_BLOQUE_TENTATIVES,
    STATUT_DISABLED,
    STATUT_MFA_SETUP_REQUIRED,
    STATUT_PENDING_ACTIVATION,
    STATUT_SUPPRIME,
    TOKEN_PASSWORD_RESET_FROM_LOCKOUT,
)
from app.core.security import (
    create_access_token,
    create_scoped_token,
    decode_scoped_token,
    decrypt_secret,
    encrypt_secret,
    ensure_aware_utc,
    generate_raw_password_reset_token,
    generate_raw_session_token,
    hash_recovery_code,
    hash_session_token,
    hash_token,
    utc_now,
    verify_password,
)
from app.models.code_secours import CodeSecours
from app.models.identifiant_totp import IdentifiantTotp
from app.models.jeton_reinitialisation import JetonReinitialisationMotDePasse
from app.models.journal_audit import JournalAudit
from app.models.session_utilisateur import SessionUtilisateur
from app.models.tentative_connexion import TentativeConnexion
from app.models.utilisateur import Utilisateur
from app.services.mail_service import MailService


class AuthService:
    SECURITY_EMAIL_COOLDOWN_MINUTES = 15

    def __init__(self, db: Session):
        self.db = db
        self.mail_service = MailService()

    def login(
        self,
        email: str,
        password: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        email_clean = str(email or "").strip().lower()
        password = password or ""

        user = self._get_user_by_email(email_clean)

        if not user:
            self._save_attempt(
                email=email_clean,
                user_id=None,
                type_tentative="PASSWORD",
                success=False,
                reason="INVALID_CREDENTIALS",
                risk="MOYEN",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )
            self._audit(
                action="LOGIN_PASSWORD_FAILED_UNKNOWN_EMAIL",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="MOYEN",
                details={"email": email_clean},
            )
            self.db.commit()
            return self._json_error(
                "INVALID_CREDENTIALS",
                "Identifiants incorrects.",
                status="invalid_credentials",
                reason="bad_password",
                redirect_to="/login",
            )

        role = self._user_role(user)

        secure_link_error = self._secure_link_required_response_if_active(user, role)
        if secure_link_error:
            self.db.commit()
            return secure_link_error

        if (
            user.date_suppression is None
            and not user.est_actif
            and self._account_status(user) == STATUT_PENDING_ACTIVATION
            and user.mot_de_passe_hash
        ):
            if not verify_password(password, user.mot_de_passe_hash):
                return self._handle_password_failure(
                    user=user,
                    role=role,
                    email=email_clean,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                )

            setup_token = self._create_activation_totp_setup_token(user)
            self._audit(
                action="ACTIVATION_TOTP_SETUP_RESUMED",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="MOYEN",
                details={"role": role},
            )
            self.db.commit()
            return {
                "success": False,
                "code": "ACTIVATION_TOTP_SETUP_REQUIRED",
                "status": "activation_totp_setup_required",
                "role": role,
                "email": user.email,
                "message": "Veuillez terminer la configuration Authenticator.",
                "setup_token": setup_token,
                "redirect_to": "/activation/totp",
            }

        if user.date_suppression is not None or not user.est_actif:
            return self._inactive_account_error(user, role)

        if self._account_status(user) == STATUT_PENDING_ACTIVATION:
            return self._json_error(
                "ACCOUNT_PENDING_ACTIVATION",
                "Votre compte est en attente de première connexion.",
                redirect_to="/login",
            )

        if user.statut_compte == STATUT_MFA_SETUP_REQUIRED:
            return self._json_error(
                "TOTP_SETUP_REQUIRED",
                "Veuillez terminer la configuration de votre authentification.",
                redirect_to="/activation/totp",
            )

        if self._account_status(user) != STATUT_ACTIVE:
            if self._account_status(user) in {STATUT_DISABLED, STATUT_BLOQUE_TENTATIVES, STATUT_SUPPRIME}:
                return self._inactive_account_error(user, role)
            return self._json_error(
                "ACCOUNT_NOT_ACTIVE",
                "Compte indisponible.",
                redirect_to="/login",
            )

        if user.blocage_password_jusqu_a is not None and not self._is_locked(user.blocage_password_jusqu_a):
            if int(user.nombre_echecs_password or 0) >= 5:
                if (
                    getattr(user, "password_lockout_requires_mail_action", False)
                    and user.password_lockout_resolved_at is None
                ):
                    mail_sent = False
                    try:
                        mail_sent = self._create_lockout_reset_token_and_email(
                            user=user,
                            role=role,
                            adresse_ip=adresse_ip,
                            user_agent=user_agent,
                            now=utc_now(),
                        )
                    except SQLAlchemyError:
                        self.db.rollback()
                    now_mail = utc_now()
                    user.password_lockout_mail_sent_at = now_mail
                    user.password_lockout_mail_expires_at = now_mail + timedelta(minutes=15)
                    user.date_modification = now_mail
                    self.db.add(user)
                    self._audit(
                        action="PASSWORD_LOCKOUT_MAIL_RESENT" if mail_sent else "PASSWORD_LOCKOUT_MAIL_FAILED",
                        acteur_id=user.id,
                        cible_id=user.id,
                        adresse_ip=adresse_ip,
                        user_agent=user_agent,
                        niveau_risque="CRITIQUE",
                        details={"role": role, "reason": "password_lockout_not_resolved"},
                    )
                    self.db.commit()
                    return self._json_error(
                        "PASSWORD_LOCKOUT_NOT_RESOLVED",
                        "Vous ne pouvez plus vous connecter directement. Veuillez vérifier votre boîte mail et suivre les instructions de sécurité.",
                        status="mail_verification_required",
                        reason="password_lockout_mail_already_sent",
                        role=role,
                        mail_sent=bool(mail_sent),
                        remaining_seconds=900,
                        email_expires_in_seconds=900,
                        redirect_to="/mail-verification-required",
                    )
                user.nombre_echecs_password = 0
                user.password_lockout_requires_mail_action = False
            user.blocage_password_jusqu_a = None
            user.date_modification = utc_now()
            self.db.add(user)
            self.db.commit()

        if self._is_locked(user.blocage_password_jusqu_a):
            remaining_seconds = self._remaining_seconds(user.blocage_password_jusqu_a)
            if int(user.nombre_echecs_password or 0) >= 5:
                return self._json_error(
                    "ACCOUNT_TEMPORARILY_LOCKED",
                    "Vous ne pouvez plus vous connecter directement. Veuillez vérifier votre boîte mail et suivre les instructions de sécurité.",
                    status="mail_verification_required",
                    reason="password_lockout_mail_already_sent",
                    role=role,
                    mail_sent=False,
                    remaining_seconds=remaining_seconds,
                    temps_restant=self._format_remaining(user.blocage_password_jusqu_a),
                    redirect_to="/mail-verification-required",
                )

            return self._json_error(
                "LOGIN_DELAY_REQUIRED",
                f"Trop de tentatives incorrectes. Veuillez patienter {remaining_seconds} secondes.",
                status="password_cooldown",
                reason=(
                    "password_cooldown_30"
                    if remaining_seconds <= 35
                    else "password_cooldown_60"
                    if remaining_seconds <= 70
                    else "password_cooldown_active"
                ),
                remaining_seconds=remaining_seconds,
                temps_restant=self._format_remaining(user.blocage_password_jusqu_a),
                redirect_to="/login",
            )

        if not verify_password(password, user.mot_de_passe_hash):
            return self._handle_password_failure(
                user=user,
                role=role,
                email=email_clean,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        totp_identity = self._get_active_totp(user.id)

        if not totp_identity:
            setup_token = self._create_super_admin_mfa_setup_token(user)
            self._audit(
                action="MFA_SETUP_REQUIRED",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE",
                details={"role": role},
            )
            self.db.commit()
            return {
                "success": False,
                "code": "MFA_SETUP_REQUIRED",
                "status": "mfa_setup_required",
                "role": role,
                "message": "Configuration MFA requise.",
                "setup_token": setup_token,
                "redirect_to": "/mfa/setup",
            }

        mfa_recovery_error = self._mfa_recovery_required_response_if_active(
            user=user,
            role=role,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        if mfa_recovery_error:
            self.db.commit()
            return mfa_recovery_error

        mfa_token = create_scoped_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": role,
            },
            purpose="login_mfa",
            expires_delta=timedelta(minutes=settings.MFA_PENDING_EXPIRE_MINUTES),
        )

        self._save_attempt(
            email=user.email,
            user_id=user.id,
            type_tentative="PASSWORD",
            success=True,
            reason=None,
            risk="FAIBLE",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self._audit(
            action=(
                AUDIT_ADMIN_PASSWORD_VALID_MFA_PENDING
                if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN}
                else AUDIT_PASSWORD_VALID_MFA_PENDING
            ),
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="FAIBLE",
        )

        self.db.commit()

        return {
            "success": True,
            "code": "MFA_REQUIRED",
            "status": "mfa_required",
            "message": "Mot de passe correct. Vérification TOTP requise.",
            "mfa_token": mfa_token,
            "email": user.email,
            "role": role,
            "redirect_to": "/auth/totp",
        }

    def verify_totp_login(
        self,
        mfa_token: str,
        code: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        try:
            payload = decode_scoped_token(mfa_token, "login_mfa")
        except Exception:
            return self._json_error(
                "MFA_TOKEN_INVALID",
                "Session MFA expirée. Veuillez vous reconnecter.",
                redirect_to="/login",
            )

        user = self._get_user_by_email(str(payload.get("email", "")).lower())

        if not user:
            return self._json_error(
                "ACCOUNT_NOT_FOUND",
                "Compte introuvable.",
                redirect_to="/login",
            )

        role = self._user_role(user)

        secure_link_error = self._secure_link_required_response_if_active(user, role)
        if secure_link_error:
            self.db.commit()
            return secure_link_error

        if (
            user.blocage_totp_jusqu_a is not None
            and not self._is_locked(user.blocage_totp_jusqu_a)
            and int(user.nombre_echecs_totp or 0) < 4
        ):
            user.blocage_totp_jusqu_a = None
            user.date_modification = utc_now()
            self.db.add(user)
            self.db.commit()

        if int(user.nombre_echecs_totp or 0) >= 4:
            remaining_seconds = self._remaining_seconds(user.blocage_totp_jusqu_a)
            return self._json_error(
                "MFA_TEMPORARILY_LOCKED",
                "Vérification MFA bloquée. Veuillez vérifier votre boîte mail.",
                status="recovery_required",
                reason="mfa_blocked",
                role=role,
                mail_sent=False,
                can_use_backup_code=True,
                can_reset_mfa=True,
                remaining_seconds=remaining_seconds,
                redirect_to="/mfa-blocked",
            )

        if self._is_locked(user.blocage_totp_jusqu_a):
            remaining_seconds = self._remaining_seconds(user.blocage_totp_jusqu_a)
            return self._json_error(
                "TOTP_TEMPORARILY_LOCKED",
                f"Plusieurs codes incorrects. Veuillez patienter {remaining_seconds} secondes.",
                status="cooldown",
                reason="mfa_cooldown_active",
                remaining_seconds=remaining_seconds,
                temps_restant=self._format_remaining(user.blocage_totp_jusqu_a),
                redirect_to="/auth/totp",
            )

        totp_identity = self._get_active_totp(user.id)

        if not totp_identity:
            return self._json_error(
                "TOTP_NOT_CONFIGURED",
                "Authentification TOTP non configurée.",
                redirect_to="/activation/totp",
            )

        secret = decrypt_secret(totp_identity.secret_chiffre)

        if not secret:
            return self._json_error(
                "TOTP_SECRET_INVALID",
                "Configuration TOTP invalide.",
                redirect_to="/login",
            )

        cleaned_code = str(code or "").strip().replace(" ", "")

        if len(cleaned_code) != 6 or not cleaned_code.isdigit():
            return self._json_error(
                "MFA_INVALID",
                "Le code doit contenir 6 chiffres.",
                status="invalid_format",
                redirect_to="/auth/totp",
            )

        valid = pyotp.TOTP(secret).verify(cleaned_code, valid_window=1)

        if not valid:
            return self._handle_mfa_failure(
                user=user,
                role=role,
                type_tentative="TOTP",
                audit_action=(
                    AUDIT_ADMIN_LOGIN_TOTP_FAILED
                    if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN}
                    else AUDIT_LOGIN_TOTP_FAILED
                ),
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        now = utc_now()

        user.nombre_echecs_password = 0
        user.nombre_echecs_totp = 0
        user.recovery_code_failed_attempts = 0
        user.recovery_code_last_failure_at = None
        user.recovery_code_cooldown_until = None
        user.recovery_secure_link_required = False
        user.recovery_secure_link_expires_at = None
        user.blocage_password_jusqu_a = None
        user.blocage_totp_jusqu_a = None
        user.date_derniere_connexion = now
        user.date_modification = now

        totp_identity.date_derniere_utilisation = now
        totp_identity.date_modification = now

        self.db.add(user)
        self.db.add(totp_identity)

        access_token = self._create_final_session(
            user=user,
            role=role,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            methode_mfa="TOTP",
        )

        self._save_attempt(
            email=user.email,
            user_id=user.id,
            type_tentative="TOTP",
            success=True,
            reason=None,
            risk="FAIBLE",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self._audit(
            action=AUDIT_ADMIN_LOGIN_SUCCESS if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN} else AUDIT_LOGIN_SUCCESS,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="FAIBLE",
        )

        self.db.commit()

        return {
            "success": True,
            "code": "LOGIN_SUCCESS",
            "message": "Connexion réussie.",
            "access_token": access_token,
            "token_type": "bearer",
            "role": role,
            "redirect_to": self._dashboard_path(role),
        }

    def verify_recovery_code_login(
        self,
        mfa_token: str | None,
        code_secours: str | None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        if not mfa_token:
            return self._json_error(
                "MFA_TOKEN_MISSING",
                "Session de vérification introuvable. Veuillez recommencer la connexion.",
                status="missing_mfa_token",
                redirect_to="/login",
            )

        try:
            payload = decode_scoped_token(mfa_token, "login_mfa")
        except Exception:
            return self._json_error(
                "MFA_TOKEN_INVALID",
                "Votre session de vérification a expiré. Veuillez vous reconnecter.",
                status="mfa_session_expired",
                redirect_to="/login",
            )

        user = self._get_user_by_email(str(payload.get("email", "")).lower())

        if not user:
            return self._json_error(
                "ACCOUNT_NOT_FOUND",
                "Compte introuvable.",
                redirect_to="/login",
            )

        role = self._user_role(user)

        secure_link_error = self._secure_link_required_response_if_active(user, role)
        if secure_link_error:
            self.db.commit()
            return secure_link_error

        if not user.est_actif or user.date_suppression is not None:
            return self._inactive_account_error(user, role, redirect_to="/account-disabled")

        after_mfa_blocked = int(user.nombre_echecs_totp or 0) >= 4 or self._is_locked(user.blocage_totp_jusqu_a)
        if self._is_locked(user.recovery_code_cooldown_until):
            remaining_seconds = self._remaining_seconds(user.recovery_code_cooldown_until)
            if after_mfa_blocked:
                if remaining_seconds <= 35:
                    message = "Trop de codes de secours invalides. Veuillez patienter 30 secondes avant de réessayer."
                    reason = "recovery_code_cooldown_30s"
                elif remaining_seconds <= 70:
                    message = "Trop de codes de secours invalides. Veuillez patienter 60 secondes avant de réessayer."
                    reason = "recovery_code_cooldown_60s"
                else:
                    message = "Code de secours invalide ou déjà utilisé. Veuillez patienter 5 minutes avant de réessayer."
                    reason = "recovery_code_cooldown_5min"
                return self._json_error(
                    "RECOVERY_CODE_COOLDOWN",
                    message,
                    status="cooldown",
                    reason=reason,
                    remaining_seconds=remaining_seconds,
                    redirect_to="/auth/recovery-code",
                )
            return self._json_error(
                "RECOVERY_CODE_COOLDOWN",
                "Vous avez saisi plusieurs codes de secours invalides. Veuillez utiliser votre application Authenticator pour continuer.",
                status="recovery_code_direct_blocked",
                reason="direct_recovery_code_disabled",
                remaining_seconds=remaining_seconds,
                redirect_to="/auth/totp",
            )
        if user.recovery_code_cooldown_until is not None:
            user.recovery_code_cooldown_until = None
            user.date_modification = utc_now()
            self.db.add(user)
            self.db.commit()

        clean_code = str(code_secours or "").strip().replace(" ", "").upper()
        if len(clean_code) < 6 or len(clean_code) > 30:
            return self._json_error(
                "RECOVERY_CODE_INVALID_FORMAT",
                "Format du code de secours invalide.",
                status="invalid_format",
                redirect_to="/auth/recovery-code",
            )

        remaining_codes = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > utc_now()))
            .count()
        )

        if remaining_codes <= 0:
            self._audit(
                action="LOGIN_RECOVERY_CODE_NO_CODES_AVAILABLE",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE",
            )
            self.db.commit()

            return self._json_error(
                "NO_RECOVERY_CODES_AVAILABLE",
                "Aucun code de secours disponible. Tous vos codes de secours ont déjà été utilisés. Veuillez utiliser votre application Authenticator pour vous connecter. Après connexion, régénérez vos codes de secours depuis votre espace sécurité.",
                status="no_recovery_codes_available",
                redirect_to="/auth/totp",
            )

        code_hash = hash_recovery_code(clean_code)

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
            return self._handle_recovery_code_failure(
                user=user,
                role=role,
                after_mfa_blocked=after_mfa_blocked,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        now = utc_now()

        recovery.utilise = True
        recovery.est_utilise = True
        recovery.utilise_a = now

        user.nombre_echecs_password = 0
        user.nombre_echecs_totp = 0
        user.recovery_code_failed_attempts = 0
        user.recovery_code_last_failure_at = None
        user.recovery_code_cooldown_until = None
        user.recovery_secure_link_required = False
        user.recovery_secure_link_expires_at = None
        user.blocage_password_jusqu_a = None
        user.blocage_totp_jusqu_a = None
        user.date_derniere_connexion = now
        user.date_modification = now

        self.db.add(recovery)
        self.db.add(user)

        access_token = self._create_final_session(
            user=user,
            role=self._user_role(user),
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            methode_mfa="RECOVERY_CODE",
        )

        self._save_attempt(
            email=user.email,
            user_id=user.id,
            type_tentative="RECOVERY_CODE",
            success=True,
            reason=None,
            risk="MOYEN",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self._audit(
            action="LOGIN_RECOVERY_CODE_SUCCESS",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"remaining_codes_before_login": remaining_codes},
        )

        self._safe_mail_send(
            lambda: self.mail_service.send_security_alert_email(
                to_email=user.email,
                subject="Connexion avec code de secours",
                message=(
                    "Un code de secours a été utilisé pour se connecter à votre compte. "
                    "Si ce n’était pas vous, contactez immédiatement l'administrateur."
                ),
                db=None,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={
                    "type": "RECOVERY_CODE_LOGIN",
                    "remaining_after": max(remaining_codes - 1, 0),
                },
            ),
            action="RECOVERY_CODE_LOGIN_ALERT_EMAIL_EXCEPTION",
            user=user,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self.db.commit()

        return {
            "success": True,
            "code": "LOGIN_SUCCESS",
            "status": "success",
            "message": "Code de secours validé.",
            "access_token": access_token,
            "token_type": "bearer",
            "role": role,
            "user": {"email": user.email, "role": role},
            "redirect_to": self._dashboard_path(role),
        }

    def logout(self, user: Utilisateur):
        role = self._user_role(user)

        self.db.query(SessionUtilisateur).filter(
            SessionUtilisateur.utilisateur_id == user.id,
            SessionUtilisateur.revoque_a.is_(None),
            SessionUtilisateur.statut_session == SESSION_ACTIVE,
        ).update(
            {
                "statut_session": SESSION_REVOKED,
                "revoque_a": utc_now(),
                "raison_revocation": "Déconnexion utilisateur",
            },
            synchronize_session=False,
        )

        self._audit(
            action="ADMIN_LOGOUT" if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN} else "USER_LOGOUT",
            acteur_id=user.id,
            cible_id=user.id,
            niveau_risque="FAIBLE",
        )

        self.db.commit()

        return {
            "success": True,
            "message": "Déconnexion réussie.",
        }

    def verify_admin_mfa_backup_code_link(
        self,
        token: str,
        code_secours: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        token_row = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(token))
            .filter(JetonReinitialisationMotDePasse.type_jeton == "MFA_BACKUP_CODE")
            .first()
        )

        now = utc_now()
        if not token_row:
            return self._json_error(
                "MFA_BACKUP_CODE_LINK_INVALID",
                "Lien invalide. Veuillez recommencer la connexion.",
                status="invalid_token",
                redirect_to="/login",
            )
        if ensure_aware_utc(token_row.expire_a) <= now:
            return self._json_error(
                "MFA_BACKUP_CODE_LINK_EXPIRED",
                "Ce lien de récupération a expiré. Veuillez recommencer la connexion.",
                status="token_expired",
                redirect_to="/login",
            )
        if token_row.utilise_a is not None:
            return self._json_error(
                "MFA_BACKUP_CODE_LINK_USED",
                "Ce lien a déjà été utilisé. Veuillez recommencer la connexion.",
                status="token_used",
                redirect_to="/login",
            )

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == token_row.utilisateur_id)
            .filter(Utilisateur.role.in_([ROLE_USER, ROLE_ADMIN, ROLE_SUPER_ADMIN]))
            .filter(Utilisateur.est_actif.is_(True))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        if not user:
            return self._json_error(
                "ACCOUNT_NOT_FOUND",
                "Compte introuvable.",
                status="invalid_or_expired_token",
                redirect_to="/login",
            )

        role = self._user_role(user)
        if self._is_locked(user.recovery_code_cooldown_until):
            remaining_seconds = self._remaining_seconds(user.recovery_code_cooldown_until)
            if remaining_seconds <= 35:
                message = "Trop de codes de secours invalides. Veuillez patienter 30 secondes avant de réessayer."
                reason = "recovery_code_cooldown_30s"
            elif remaining_seconds <= 70:
                message = "Trop de codes de secours invalides. Veuillez patienter 60 secondes avant de réessayer."
                reason = "recovery_code_cooldown_60s"
            else:
                message = "Code de secours invalide ou déjà utilisé. Veuillez patienter 5 minutes avant de réessayer."
                reason = "recovery_code_cooldown_5min"
            return self._json_error(
                "RECOVERY_CODE_COOLDOWN",
                message,
                status="cooldown",
                reason=reason,
                remaining_seconds=remaining_seconds,
                redirect_to="/mfa/recovery-code",
            )
        if user.recovery_code_cooldown_until is not None:
            user.recovery_code_cooldown_until = None
            user.date_modification = now
            self.db.add(user)
            self.db.flush()

        clean_code = str(code_secours or "").strip().replace(" ", "").upper()
        if len(clean_code) < 6 or len(clean_code) > 30:
            return self._json_error(
                "RECOVERY_CODE_INVALID_FORMAT",
                "Format du code de secours invalide.",
                status="invalid_format",
                redirect_to="/mfa/recovery-code",
            )

        remaining_codes = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > utc_now()))
            .count()
        )
        if remaining_codes <= 0:
            return self._json_error(
                "NO_RECOVERY_CODES_AVAILABLE",
                "Vous ne disposez plus de codes de secours valides.",
                status="no_recovery_codes_available",
                redirect_to="/login",
            )

        recovery = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.code_hash == hash_recovery_code(clean_code))
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > utc_now()))
            .first()
        )

        if not recovery:
            return self._handle_recovery_code_failure(
                user=user,
                role=role,
                after_mfa_blocked=True,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                redirect_to="/mfa/recovery-code",
            )

        recovery.utilise = True
        recovery.est_utilise = True
        recovery.utilise_a = now
        token_row.utilise_a = now
        user.nombre_echecs_password = 0
        user.nombre_echecs_totp = 0
        user.blocage_totp_jusqu_a = None
        user.recovery_code_failed_attempts = 0
        user.recovery_code_last_failure_at = None
        user.recovery_code_cooldown_until = None
        user.recovery_secure_link_required = False
        user.recovery_secure_link_expires_at = None
        user.blocage_password_jusqu_a = None
        user.date_derniere_connexion = now
        user.date_modification = now

        self.db.add(recovery)
        self.db.add(token_row)
        self.db.add(user)
        access_token = self._create_final_session(
            user=user,
            role=role,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            methode_mfa="RECOVERY_CODE",
        )
        self._save_attempt(
            email=user.email,
            user_id=user.id,
            type_tentative="RECOVERY_CODE",
            success=True,
            reason=None,
            risk="MOYEN",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        self._audit(
            action="MFA_BACKUP_CODE_SUCCESS",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"source": "email_link"},
        )
        self.db.commit()

        return {
            "success": True,
            "code": "LOGIN_SUCCESS",
            "status": "success",
            "message": "Connexion validée avec un code de secours.",
            "access_token": access_token,
            "token_type": "bearer",
            "role": role,
            "user": {"role": role, "email": user.email},
            "redirect_to": self._dashboard_path(role),
        }

    def start_super_admin_mfa_setup(
        self,
        setup_token: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        payload, user, error = self._decode_super_admin_mfa_setup_token(setup_token)
        if error:
            return error

        active_totp = self._get_active_totp(user.id)
        if active_totp:
            return self._json_error(
                "MFA_ALREADY_CONFIGURED",
                "La MFA est deja configuree pour ce compte.",
                status="mfa_already_configured",
                redirect_to="/auth/totp",
            )

        setup_id = str(payload.get("setup_id") or "")
        role = self._user_role(user)
        now = utc_now()
        secret = pyotp.random_base32()
        encrypted_secret = encrypt_secret(secret)

        totp_identity = (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user.id)
            .first()
        )
        if totp_identity and totp_identity.dernier_pas_utilise == f"cancelled:{setup_id}":
            return self._json_error(
                "MFA_SETUP_TOKEN_CANCELLED",
                "Session de configuration annulee. Veuillez vous reconnecter.",
                status="setup_cancelled",
                redirect_to="/login",
            )
        if not totp_identity:
            totp_identity = IdentifiantTotp(
                utilisateur_id=user.id,
                secret_chiffre=encrypted_secret,
                est_actif=False,
                date_creation=now,
            )
        else:
            totp_identity.secret_chiffre = encrypted_secret
            totp_identity.est_actif = False
        totp_identity.date_activation = None
        totp_identity.date_revocation = None
        totp_identity.date_derniere_utilisation = None
        totp_identity.dernier_pas_utilise = f"setup:{setup_id}"
        totp_identity.date_modification = now

        user.nombre_echecs_totp = 0
        user.blocage_totp_jusqu_a = None
        user.date_modification = now

        self.db.add(totp_identity)
        self.db.add(user)
        self._audit(
            action="MFA_SETUP_STARTED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"role": role, "setup_id": setup_id},
        )
        self.db.commit()

        otpauth_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=settings.TOTP_ISSUER_NAME,
        )
        return {
            "success": True,
            "code": "MFA_SETUP_STARTED",
            "status": "mfa_setup_started",
            "message": "Scannez le QR code avec Google Authenticator ou Microsoft Authenticator.",
            "otpauth_uri": otpauth_uri,
            "qr_code": self._make_qr_base64(otpauth_uri),
            "qr_code_base64": self._make_qr_base64(otpauth_uri),
            "role": role,
        }

    def confirm_super_admin_mfa_setup(
        self,
        setup_token: str,
        code: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        payload, user, error = self._decode_super_admin_mfa_setup_token(setup_token)
        if error:
            return error

        if self._get_active_totp(user.id):
            return self._json_error(
                "MFA_ALREADY_CONFIGURED",
                "La MFA est deja configuree pour ce compte.",
                status="mfa_already_configured",
                redirect_to="/auth/totp",
            )

        setup_id = str(payload.get("setup_id") or "")
        role = self._user_role(user)
        now = utc_now()
        if self._is_locked(user.blocage_totp_jusqu_a):
            return self._json_error(
                "MFA_SETUP_COOLDOWN",
                "Plusieurs codes incorrects. Veuillez patienter 60 secondes.",
                status="cooldown",
                reason="mfa_setup_cooldown_60s",
                remaining_seconds=self._remaining_seconds(user.blocage_totp_jusqu_a),
                redirect_to="/mfa/setup",
            )
        if user.blocage_totp_jusqu_a is not None:
            user.blocage_totp_jusqu_a = None
            self.db.add(user)
            self.db.flush()

        clean_code = str(code or "").strip().replace(" ", "")
        if len(clean_code) != 6 or not clean_code.isdigit():
            return self._json_error(
                "MFA_SETUP_INVALID_FORMAT",
                "Le code doit contenir 6 chiffres.",
                status="invalid_format",
                redirect_to="/mfa/setup",
            )

        totp_identity = (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user.id)
            .filter(IdentifiantTotp.est_actif.is_(False))
            .filter(IdentifiantTotp.date_revocation.is_(None))
            .first()
        )
        if not totp_identity or totp_identity.dernier_pas_utilise != f"setup:{setup_id}":
            return self._json_error(
                "MFA_SETUP_NOT_STARTED",
                "Veuillez generer un nouveau QR code.",
                status="setup_not_started",
                redirect_to="/mfa/setup",
            )

        secret = decrypt_secret(totp_identity.secret_chiffre)
        if not secret:
            return self._json_error(
                "MFA_SETUP_SECRET_INVALID",
                "Configuration MFA invalide. Veuillez recommencer.",
                status="setup_not_started",
                redirect_to="/mfa/setup",
            )

        totp = pyotp.TOTP(secret)
        if not totp.verify(clean_code, valid_window=1):
            attempts = int(user.nombre_echecs_totp or 0) + 1
            user.nombre_echecs_totp = attempts
            user.date_modification = now
            self.db.add(user)
            self._audit(
                action="MFA_SETUP_FAILED",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE" if attempts < 4 else "CRITIQUE",
                details={"attempt": attempts, "role": role},
            )
            if attempts == 3:
                user.blocage_totp_jusqu_a = now + timedelta(seconds=60)
                self.db.commit()
                return self._json_error(
                    "MFA_SETUP_COOLDOWN",
                    "Plusieurs codes incorrects. Veuillez patienter 60 secondes.",
                    status="cooldown",
                    reason="mfa_setup_cooldown_60s",
                    attempts=attempts,
                    remaining_seconds=60,
                    redirect_to="/mfa/setup",
                )
            if attempts >= 4:
                totp_identity.date_revocation = now
                totp_identity.dernier_pas_utilise = f"cancelled:{setup_id}"
                totp_identity.date_modification = now
                user.nombre_echecs_totp = 0
                user.blocage_totp_jusqu_a = None
                self.db.add(totp_identity)
                self.db.add(user)
                self.db.commit()
                return self._json_error(
                    "MFA_SETUP_CANCELLED",
                    "Trop de codes incorrects. Veuillez recommencer la connexion.",
                    status="setup_cancelled",
                    reason="too_many_mfa_setup_failures",
                    redirect_to="/login",
                )
            self.db.commit()
            return self._json_error(
                "MFA_SETUP_INVALID_CODE",
                "Code incorrect. Veuillez reessayer.",
                status="invalid_code",
                attempts=attempts,
                redirect_to="/mfa/setup",
            )

        time_step = str(pyotp.TOTP(secret).timecode(now))
        totp_identity.est_actif = True
        totp_identity.date_activation = now
        totp_identity.date_derniere_utilisation = now
        totp_identity.date_revocation = None
        totp_identity.dernier_pas_utilise = time_step
        totp_identity.date_modification = now

        self.db.query(CodeSecours).filter(
            CodeSecours.utilisateur_id == user.id,
            CodeSecours.utilise.is_(False),
            CodeSecours.est_utilise.is_(False),
        ).update(
            {"utilise": True, "est_utilise": True, "utilise_a": now},
            synchronize_session=False,
        )

        recovery_codes = []
        for _ in range(10):
            raw_code = self._generate_recovery_code()
            recovery_codes.append(raw_code)
            self.db.add(
                CodeSecours(
                    utilisateur_id=user.id,
                    code_hash=hash_recovery_code(raw_code),
                    utilise=False,
                    est_utilise=False,
                    utilise_a=None,
                )
            )

        user.nombre_echecs_password = 0
        user.nombre_echecs_totp = 0
        user.blocage_password_jusqu_a = None
        user.blocage_totp_jusqu_a = None
        user.date_derniere_connexion = now
        user.date_modification = now

        self.db.add(totp_identity)
        self.db.add(user)
        access_token = self._create_final_session(
            user=user,
            role=role,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            methode_mfa="TOTP_SETUP",
        )
        self._audit(
            action="MFA_SETUP_SUCCESS",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"role": role},
        )
        self._audit(
            action="RECOVERY_CODES_GENERATED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"count": len(recovery_codes), "role": role},
        )
        self.db.commit()

        return {
            "success": True,
            "code": "MFA_SETUP_SUCCESS",
            "status": "success",
            "message": "MFA configuree avec succes.",
            "access_token": access_token,
            "token_type": "bearer",
            "role": role,
            "user": {"role": role, "email": user.email},
            "recovery_codes": recovery_codes,
            "redirect_to": self._dashboard_path(role),
        }

    def verify_admin_mfa_reset_recovery_code(
        self,
        token: str,
        recovery_code: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        token_row, user, error = self._get_admin_mfa_reset_token(token)
        if error:
            return error

        now = utc_now()
        if self._is_locked(user.recovery_code_cooldown_until):
            remaining_seconds = self._remaining_seconds(user.recovery_code_cooldown_until)
            if remaining_seconds <= 35:
                message = "Trop de codes de secours invalides. Veuillez patienter 30 secondes avant de réessayer."
                reason = "recovery_code_cooldown_30s"
            elif remaining_seconds <= 70:
                message = "Trop de codes de secours invalides. Veuillez patienter 60 secondes avant de réessayer."
                reason = "recovery_code_cooldown_60s"
            else:
                message = "Code de secours invalide ou déjà utilisé. Veuillez patienter 5 minutes avant de réessayer."
                reason = "recovery_code_cooldown_5min"
            return self._json_error(
                "MFA_RESET_RECOVERY_COOLDOWN",
                message,
                status="cooldown",
                reason=reason,
                remaining_seconds=remaining_seconds,
                redirect_to="/mfa/reset",
            )
        if user.recovery_code_cooldown_until is not None:
            user.recovery_code_cooldown_until = None
            user.date_modification = now
            self.db.add(user)
            self.db.flush()

        clean_code = str(recovery_code or "").strip().replace(" ", "").upper()
        if len(clean_code) < 6:
            return self._json_error(
                "MFA_RESET_RECOVERY_INVALID_FORMAT",
                "Format du code de secours invalide.",
                status="invalid_format",
                redirect_to="/mfa/reset",
            )

        remaining_codes = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > now))
            .count()
        )
        if remaining_codes <= 0:
            return self._json_error(
                "NO_RECOVERY_CODES_AVAILABLE",
                "Vous ne disposez plus de codes de secours valides.",
                status="no_recovery_codes_available",
                redirect_to="/mfa/reset",
            )

        recovery = (
            self.db.query(CodeSecours)
            .filter(CodeSecours.utilisateur_id == user.id)
            .filter(CodeSecours.code_hash == hash_recovery_code(clean_code))
            .filter(CodeSecours.utilise.is_(False))
            .filter(CodeSecours.est_utilise.is_(False))
            .filter((CodeSecours.date_expiration.is_(None)) | (CodeSecours.date_expiration > now))
            .first()
        )

        if not recovery:
            return self._handle_recovery_code_failure(
                user=user,
                role=self._user_role(user),
                after_mfa_blocked=True,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                redirect_to="/mfa/reset",
            )

        secret = pyotp.random_base32()
        otpauth_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=settings.TOTP_ISSUER_NAME,
        )
        details = dict(token_row.details or {})
        details["pending_totp_secret"] = secret
        details["recovery_code_verified_at"] = now.isoformat()
        token_row.details = details

        recovery.utilise = True
        recovery.est_utilise = True
        recovery.utilise_a = now
        token_row.mfa_echecs_recovery = 0
        token_row.mfa_recovery_bloque_jusqu_a = None
        user.recovery_code_failed_attempts = 0
        user.recovery_code_last_failure_at = None
        user.recovery_code_cooldown_until = None
        user.date_modification = now
        self.db.add(recovery)
        self.db.add(token_row)
        self.db.add(user)
        self._audit(
            action="MFA_RESET_RECOVERY_CODE_SUCCESS",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"source": "mfa_reset"},
        )
        self.db.commit()

        return {
            "success": True,
            "code": "MFA_RESET_QR_READY",
            "status": "success_show_qr",
            "message": "Code de secours valide. Scannez le nouveau QR code.",
            "otpauth_uri": otpauth_uri,
            "qr_code_base64": self._make_qr_base64(otpauth_uri),
        }

    def confirm_admin_mfa_reset(
        self,
        token: str,
        code: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        token_row, user, error = self._get_admin_mfa_reset_token(token)
        if error:
            return error

        details = dict(token_row.details or {})
        secret = details.get("pending_totp_secret")
        if not secret:
            return self._json_error(
                "MFA_RESET_RECOVERY_REQUIRED",
                "Veuillez d'abord valider un code de secours.",
                status="recovery_required",
                redirect_to="/mfa/reset",
            )

        now = utc_now()
        if self._is_locked(token_row.mfa_cooldown_jusqu_a):
            return self._json_error(
                "MFA_RESET_NEW_TOTP_COOLDOWN",
                "Plusieurs codes incorrects. Veuillez patienter 60 secondes.",
                status="cooldown",
                reason="new_mfa_code_cooldown",
                remaining_seconds=self._remaining_seconds(token_row.mfa_cooldown_jusqu_a),
                redirect_to="/mfa/reset",
            )
        if token_row.mfa_cooldown_jusqu_a is not None:
            token_row.mfa_cooldown_jusqu_a = None
            self.db.add(token_row)
            self.db.flush()

        clean_code = str(code or "").strip().replace(" ", "")
        if len(clean_code) != 6 or not clean_code.isdigit():
            return self._json_error(
                "MFA_RESET_CODE_INVALID_FORMAT",
                "Le code doit contenir 6 chiffres.",
                status="invalid_format",
                redirect_to="/mfa/reset",
            )

        if not pyotp.TOTP(secret).verify(clean_code, valid_window=1):
            attempts = int(token_row.mfa_echecs_totp or 0) + 1
            token_row.mfa_echecs_totp = attempts
            self.db.add(token_row)
            self._audit(
                action="MFA_RESET_NEW_TOTP_FAILURE",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="CRITIQUE" if attempts >= 4 else "ELEVE",
                details={"attempt": attempts},
            )
            if attempts == 3:
                token_row.mfa_cooldown_jusqu_a = now + timedelta(seconds=60)
                self.db.commit()
                return self._json_error(
                    "MFA_RESET_NEW_TOTP_COOLDOWN",
                    "Plusieurs codes incorrects. Veuillez patienter 60 secondes.",
                    status="cooldown",
                    reason="new_mfa_code_cooldown",
                    attempts=attempts,
                    remaining_seconds=60,
                    redirect_to="/mfa/reset",
                )
            if attempts >= 4:
                details.pop("pending_totp_secret", None)
                details["mfa_reset_failed_at"] = now.isoformat()
                token_row.details = details
                token_row.utilise_a = now
                mail_sent = self.mail_service.send_mfa_reset_failed_email(
                    to_email=user.email,
                    db=self.db,
                    utilisateur_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                )
                self._audit(
                    action="MFA_RESET_FAILED",
                    acteur_id=user.id,
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="CRITIQUE",
                    details={"attempt": attempts, "mail_sent": bool(mail_sent)},
                )
                self.db.commit()
                return self._json_error(
                    "MFA_RESET_FAILED",
                    "La réinitialisation MFA a été interrompue pour des raisons de sécurité. Veuillez vérifier votre boîte mail.",
                    status="mfa_reset_failed",
                    reason="too_many_new_mfa_failures",
                    attempts=attempts,
                    mail_sent=bool(mail_sent),
                    redirect_to="/login",
                )
            self.db.commit()
            return self._json_error(
                "MFA_RESET_NEW_TOTP_INVALID",
                "Code incorrect. Vérifiez votre application Authenticator.",
                status="invalid_code",
                reason="new_mfa_code_invalid",
                attempts=attempts,
                redirect_to="/mfa/reset",
            )

        totp_identity = (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user.id)
            .first()
        )
        if not totp_identity:
            totp_identity = IdentifiantTotp(utilisateur_id=user.id)

        totp_identity.secret_chiffre = encrypt_secret(secret)
        totp_identity.est_actif = True
        totp_identity.date_activation = now
        totp_identity.date_revocation = None
        totp_identity.date_modification = now
        totp_identity.dernier_pas_utilise = None

        self.db.query(CodeSecours).filter(
            CodeSecours.utilisateur_id == user.id,
            CodeSecours.utilise.is_(False),
            CodeSecours.est_utilise.is_(False),
        ).update(
            {"utilise": True, "est_utilise": True, "utilise_a": now},
            synchronize_session=False,
        )

        raw_codes = []
        for _ in range(10):
            raw_code = self._generate_recovery_code()
            raw_codes.append(raw_code)
            self.db.add(
                CodeSecours(
                    utilisateur_id=user.id,
                    code_hash=hash_recovery_code(raw_code),
                    utilise=False,
                    est_utilise=False,
                    utilise_a=None,
                )
            )

        user.nombre_echecs_totp = 0
        user.blocage_totp_jusqu_a = None
        user.recovery_code_failed_attempts = 0
        user.recovery_code_last_failure_at = None
        user.recovery_code_cooldown_until = None
        user.recovery_secure_link_required = False
        user.recovery_secure_link_expires_at = None
        token_row.utilise_a = now
        details.pop("pending_totp_secret", None)
        token_row.details = details

        self.db.add(totp_identity)
        self.db.add(user)
        self.db.add(token_row)
        self.mail_service.send_recovery_codes_email(
            to_email=user.email,
            recovery_codes=raw_codes,
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            role=self._user_role(user),
        )
        self.mail_service.send_mfa_reset_success_email(
            to_email=user.email,
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        self._audit(
            action="MFA_RESET_SUCCESS",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"recovery_codes_regenerated": True},
        )
        self._audit(
            action="MFA_RECOVERY_CODES_REGENERATED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"count": len(raw_codes)},
        )
        self.db.commit()

        return {
            "success": True,
            "code": "MFA_RESET_SUCCESS",
            "status": "success",
            "message": "Votre MFA a été réinitialisée avec succès.",
            "redirect_to": "/login",
        }

    def _handle_admin_password_failure(
        self,
        user: Utilisateur,
        role: str,
        email: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        new_count = int(user.nombre_echecs_password or 0) + 1
        if new_count >= 5:
            new_count = 5
        user.nombre_echecs_password = new_count
        user.date_modification = now

        if new_count == 3:
            user.blocage_password_jusqu_a = now + timedelta(seconds=30)
            action = "PASSWORD_COOLDOWN_30S"
            message = "Plusieurs tentatives incorrectes. Veuillez patienter 30 secondes."
            reason = "password_cooldown_30s"
            status = "password_cooldown"
            remaining_seconds = 30
            risk = "MOYEN"
        elif new_count == 4:
            user.blocage_password_jusqu_a = now + timedelta(seconds=60)
            action = "PASSWORD_COOLDOWN_60S"
            message = "Nouvelle tentative incorrecte. Veuillez patienter 60 secondes."
            reason = "password_cooldown_60s"
            status = "password_cooldown"
            remaining_seconds = 60
            risk = "ELEVE"
        elif new_count >= 5:
            user.blocage_password_jusqu_a = now + timedelta(minutes=15)
            user.date_derniere_alerte_securite = now
            user.password_lockout_requires_mail_action = True
            user.password_lockout_resolved_at = None
            user.password_lockout_mail_sent_at = now
            user.password_lockout_mail_expires_at = now + timedelta(minutes=15)
            action = "PASSWORD_LOCKOUT"
            message = "Compte temporairement bloque. Veuillez verifier votre boite mail."
            reason = "password_blocked"
            status = "password_lockout"
            remaining_seconds = 900
            risk = "CRITIQUE"
        else:
            user.blocage_password_jusqu_a = None
            action = "PASSWORD_FAILURE"
            message = "Identifiants incorrects."
            reason = "bad_password"
            status = "invalid_credentials"
            remaining_seconds = None
            risk = "MOYEN"

        self.db.add(user)
        self._save_attempt(
            email=email,
            user_id=user.id,
            type_tentative="PASSWORD",
            success=False,
            reason="BAD_PASSWORD",
            risk=risk,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        self._audit(
            action=action,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque=risk,
            details={"attempt": new_count, "role": role},
        )

        mail_sent = None
        if new_count >= 5:
            self._revoke_user_sessions_on_security_lock(user)
            self.db.commit()

            try:
                mail_sent = self._create_lockout_reset_token_and_email(
                    user=user,
                    role=role,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    now=now,
                )
                self._audit(
                    action=(
                        "PASSWORD_LOCKOUT_EMAIL_SENT"
                        if mail_sent
                        else "PASSWORD_LOCKOUT_EMAIL_FAILED"
                    ),
                    acteur_id=user.id,
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque=("ELEVE" if mail_sent else "CRITIQUE"),
                    details={"attempt": new_count, "role": role},
                )
                self.db.commit()
            except SQLAlchemyError as exc:
                self.db.rollback()
                print("ERREUR ADMIN LOCKOUT TOKEN/MAIL:", repr(exc))
                mail_sent = False
                try:
                    self._audit(
                        action="PASSWORD_LOCKOUT_EMAIL_FAILED",
                        acteur_id=user.id,
                        cible_id=user.id,
                        adresse_ip=adresse_ip,
                        user_agent=user_agent,
                        niveau_risque="CRITIQUE",
                        details={
                            "attempt": new_count,
                            "role": role,
                            "error": exc.__class__.__name__,
                        },
                    )
                    self.db.commit()
                except Exception:
                    self.db.rollback()

            if not mail_sent:
                message = (
                    "Compte temporairement bloque. L'email de securite "
                    "n'a pas pu etre envoye. Veuillez contacter l'administrateur systeme."
                )
        else:
            self.db.commit()

        extra = {
            "status": status,
            "reason": reason,
            "role": role,
            "redirect_to": "/login",
        }
        if remaining_seconds is not None:
            extra["remaining_seconds"] = remaining_seconds
            extra["temps_restant"] = (
                f"{remaining_seconds // 60:02d}:{remaining_seconds % 60:02d}"
            )
        if mail_sent is not None:
            extra["mail_sent"] = bool(mail_sent)

        code = (
            "ACCOUNT_TEMPORARILY_LOCKED"
            if status == "password_lockout"
            else "LOGIN_DELAY_REQUIRED"
            if status == "password_cooldown"
            else "INVALID_CREDENTIALS"
        )
        return self._json_error(code, message, **extra)

    def _handle_admin_mfa_failure(
        self,
        user: Utilisateur,
        type_tentative: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        role = self._user_role(user)
        new_count = int(user.nombre_echecs_totp or 0) + 1
        user.nombre_echecs_totp = new_count
        user.date_modification = now

        if new_count == 3:
            user.blocage_totp_jusqu_a = now + timedelta(seconds=60)
            action = "MFA_COOLDOWN_60S"
            risk = "ELEVE"
            response = self._json_error(
                "MFA_DELAY_REQUIRED",
                "Plusieurs codes incorrects. Veuillez patienter 60 secondes.",
                status="cooldown",
                reason="mfa_cooldown_60s",
                attempts=new_count,
                remaining_seconds=60,
                temps_restant="01:00",
                redirect_to="/auth/totp",
            )
        elif new_count >= 4:
            user.est_actif = False
            user.statut_compte = STATUT_BLOQUE_TENTATIVES
            user.date_desactivation = now
            user.blocage_totp_jusqu_a = now + timedelta(minutes=15)
            user.recovery_code_failed_attempts = 0
            user.recovery_code_last_failure_at = None
            user.recovery_code_cooldown_until = None
            user.recovery_code_alert_sent_at = None
            action = "MFA_BLOCKED"
            risk = "CRITIQUE"
            backup_link, reset_link = self._create_admin_mfa_recovery_links(
                user=user,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                now=now,
            )
            mail_sent = self._safe_mail_send(
                lambda: self.mail_service.send_admin_mfa_blocked_email(
                    to_email=user.email,
                    backup_code_link=backup_link,
                    mfa_reset_link=reset_link,
                    db=self.db,
                    utilisateur_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    role=role,
                ),
                action="MFA_BLOCKED_EMAIL_EXCEPTION",
                user=user,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"attempt": new_count, "type": type_tentative},
            )
            self._audit(
                action="MFA_BLOCKED_EMAIL_SENT" if mail_sent else "MFA_BLOCKED_EMAIL_FAILED",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=("ELEVE" if mail_sent else "CRITIQUE"),
                details={"attempt": new_count, "type": type_tentative},
            )
            self._revoke_user_sessions_on_security_lock(user)
            response = self._json_error(
                "MFA_TEMPORARILY_LOCKED",
                "Vérification MFA bloquée. Veuillez vérifier votre boîte mail.",
                status="recovery_required",
                reason="mfa_blocked",
                role=role,
                attempts=new_count,
                mail_sent=bool(mail_sent),
                can_use_backup_code=True,
                can_reset_mfa=True,
                remaining_seconds=900,
                expires_in_seconds=900,
                redirect_to="/mfa-blocked",
            )
        else:
            user.blocage_totp_jusqu_a = None
            action = "MFA_FAILURE"
            risk = "MOYEN"
            response = self._json_error(
                "MFA_INVALID",
                "Code incorrect. Veuillez réessayer.",
                status="invalid_code",
                reason="mfa_invalid_code",
                attempts=new_count,
                redirect_to="/auth/totp",
            )

        self.db.add(user)
        self._save_attempt(
            email=user.email,
            user_id=user.id,
            type_tentative=type_tentative,
            success=False,
            reason=f"{type_tentative}_FAILED",
            risk=risk,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        self._audit(
            action=action,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque=risk,
            details={"attempt": new_count, "type": type_tentative},
        )
        self.db.commit()
        return response

    def _handle_password_failure(
        self,
        user: Utilisateur,
        role: str,
        email: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        current = int(user.nombre_echecs_password or 0)
        incident_recent = self._has_unresolved_reported_incident(user)

        immediate_relock = current >= 5 or incident_recent

        if immediate_relock:
            new_count = max(current, 5)
            user.est_actif = False
            user.statut_compte = STATUT_BLOQUE_TENTATIVES
            user.date_desactivation = now
            user.nombre_echecs_password = new_count
            user.blocage_password_jusqu_a = now + timedelta(minutes=15)
            user.password_lockout_requires_mail_action = True
            user.password_lockout_resolved_at = None
            user.password_lockout_mail_sent_at = now
            user.password_lockout_mail_expires_at = now + timedelta(minutes=15)
            user.date_modification = now
            self.db.add(user)

            self._save_attempt(
                email=email,
                user_id=user.id,
                type_tentative="PASSWORD",
                success=False,
                reason="PASSWORD_RELOCK_AFTER_SECURITY_EVENT",
                risk="CRITIQUE",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

            self._audit(
                action=(
                    "SECURITY_RELOCK_AFTER_REPORTED_INCIDENT"
                    if incident_recent
                    else "SECURITY_RELOCK_AFTER_LOCKOUT"
                ),
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="CRITIQUE",
                details={
                    "attempt": new_count,
                    "previous_failures": current,
                    "incident_recent": incident_recent,
                    "lock_minutes": 15,
                },
            )

            self._revoke_user_sessions_on_security_lock(user)

            mail_sent = False
            if self._should_send_security_email(user, now):
                try:
                    mail_sent = bool(self._create_lockout_reset_token_and_email(
                        user=user,
                        role=role,
                        adresse_ip=adresse_ip,
                        user_agent=user_agent,
                        now=now,
                    ))
                    user.date_derniere_alerte_securite = now
                    self.db.add(user)
                except SQLAlchemyError:
                    self.db.rollback()
                    mail_sent = False
                    user = self._get_user_by_email(email)
                    user.est_actif = False
                    user.statut_compte = STATUT_BLOQUE_TENTATIVES
                    user.date_desactivation = now
                    user.nombre_echecs_password = new_count
                    user.blocage_password_jusqu_a = now + timedelta(minutes=15)
                    user.password_lockout_requires_mail_action = True
                    user.password_lockout_resolved_at = None
                    user.password_lockout_mail_sent_at = now
                    user.password_lockout_mail_expires_at = now + timedelta(minutes=15)
                    user.date_modification = now
                    self.db.add(user)
            else:
                self._audit(
                    action="PASSWORD_LOCKOUT_SECURITY_EMAIL_THROTTLED",
                    acteur_id=user.id,
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="MOYEN",
                    details={"cooldown_minutes": self.SECURITY_EMAIL_COOLDOWN_MINUTES},
                )

            self.db.commit()

            return self._json_error(
                "ACCOUNT_TEMPORARILY_LOCKED",
                "Vous ne pouvez plus vous connecter directement. Veuillez vérifier votre boîte mail et suivre les instructions de sécurité.",
                status="password_lockout",
                reason="password_blocked",
                role=role,
                mail_sent=mail_sent,
                remaining_seconds=900,
                temps_restant="15:00",
                redirect_to="/mail-verification-required",
            )

        new_count = current + 1
        delay_seconds = 0
        lock_minutes = 0
        risk = "MOYEN"

        if new_count <= 2:
            pass
        elif new_count == 3:
            delay_seconds = 30
        elif new_count == 4:
            delay_seconds = 60
            risk = "ELEVE"
        else:
            lock_minutes = 15
            risk = "CRITIQUE"

        user.nombre_echecs_password = new_count
        user.date_modification = now

        if lock_minutes > 0:
            user.blocage_password_jusqu_a = now + timedelta(minutes=lock_minutes)
        elif delay_seconds > 0:
            user.blocage_password_jusqu_a = now + timedelta(seconds=delay_seconds)

        self.db.add(user)

        self._save_attempt(
            email=email,
            user_id=user.id,
            type_tentative="PASSWORD",
            success=False,
            reason="INVALID_CREDENTIALS",
            risk=risk,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        self._audit(
            action=(
                AUDIT_ADMIN_LOGIN_PASSWORD_FAILED
                if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN}
                else AUDIT_LOGIN_PASSWORD_FAILED
            ),
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque=risk,
            details={"attempt": new_count},
        )

        if lock_minutes > 0:
            user.est_actif = False
            user.statut_compte = STATUT_BLOQUE_TENTATIVES
            user.date_desactivation = now
            user.password_lockout_requires_mail_action = True
            user.password_lockout_resolved_at = None
            user.password_lockout_mail_sent_at = now
            user.password_lockout_mail_expires_at = now + timedelta(minutes=15)
            self._revoke_user_sessions_on_security_lock(user)

            try:
                mail_sent = self._create_lockout_reset_token_and_email(
                    user=user,
                    role=role,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    now=now,
                )
            except SQLAlchemyError:
                self.db.rollback()
                mail_sent = False
                user = self._get_user_by_email(email)
                user.est_actif = False
                user.statut_compte = STATUT_BLOQUE_TENTATIVES
                user.date_desactivation = now
                user.nombre_echecs_password = new_count
                user.blocage_password_jusqu_a = now + timedelta(minutes=15)
                user.password_lockout_requires_mail_action = True
                user.password_lockout_resolved_at = None
                user.password_lockout_mail_sent_at = now
                user.password_lockout_mail_expires_at = now + timedelta(minutes=15)
                user.date_modification = now
            user.date_derniere_alerte_securite = now
            self.db.add(user)

            self.db.commit()

            return self._json_error(
                "ACCOUNT_TEMPORARILY_LOCKED",
                "Vous ne pouvez plus vous connecter directement. Veuillez vérifier votre boîte mail et suivre les instructions de sécurité.",
                status="password_lockout",
                reason="password_blocked",
                role=role,
                mail_sent=bool(mail_sent),
                remaining_seconds=900,
                temps_restant="15:00",
                redirect_to="/mail-verification-required",
            )

        if delay_seconds > 0:
            self.db.commit()
            return self._json_error(
                "LOGIN_DELAY_REQUIRED",
                f"Trop de tentatives incorrectes. Veuillez patienter {delay_seconds} secondes.",
                status="password_cooldown",
                reason=f"password_cooldown_{delay_seconds}",
                remaining_seconds=delay_seconds,
                temps_restant=f"00:{delay_seconds:02d}" if delay_seconds < 60 else "01:00",
                redirect_to="/login",
            )

        self.db.commit()
        return self._json_error(
            "INVALID_CREDENTIALS",
            "Identifiants incorrects.",
            status="invalid_credentials",
            reason="bad_password",
            redirect_to="/login",
        )

    def _handle_mfa_failure(
        self,
        user: Utilisateur,
        role: str,
        type_tentative: str,
        audit_action: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        return self._handle_admin_mfa_failure(
            user=user,
            type_tentative=type_tentative,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

    def _handle_recovery_code_failure(
        self,
        user: Utilisateur,
        role: str,
        after_mfa_blocked: bool,
        adresse_ip: str | None,
        user_agent: str | None,
        redirect_to: str = "/auth/recovery-code",
    ):
        now = utc_now()
        attempts = int(getattr(user, "recovery_code_failed_attempts", 0) or 0) + 1
        user.recovery_code_failed_attempts = attempts
        user.recovery_code_last_failure_at = now
        user.date_modification = now

        status_value = "invalid_recovery_code"
        reason = "recovery_code_invalid_or_used"
        message = "Code de secours invalide ou déjà utilisé."
        remaining_seconds = None
        mail_sent = None
        supervisor_mail_sent = None

        if not after_mfa_blocked:
            if attempts >= 3:
                user.recovery_code_cooldown_until = now + timedelta(minutes=15)
                status_value = "recovery_code_direct_blocked"
                reason = "direct_recovery_code_disabled"
                message = "Utilisation du code de secours désactivée. Vous avez saisi plusieurs codes de secours invalides. Veuillez utiliser votre application Authenticator pour continuer."
                remaining_seconds = 900
            else:
                message = "Code de secours invalide ou déjà utilisé."
        elif role == ROLE_SUPER_ADMIN:
            if attempts == 3:
                user.recovery_code_cooldown_until = now + timedelta(seconds=30)
                status_value = "cooldown"
                reason = "recovery_code_cooldown_30s"
                message = "Trop de codes de secours invalides. Veuillez patienter 30 secondes avant de réessayer."
                remaining_seconds = 30
            elif attempts == 4:
                user.recovery_code_cooldown_until = now + timedelta(seconds=60)
                status_value = "cooldown"
                reason = "recovery_code_cooldown_60s"
                message = "Trop de codes de secours invalides. Veuillez patienter 60 secondes avant de réessayer."
                remaining_seconds = 60
            elif attempts == 5:
                mail_sent = self._safe_mail_send(
                    lambda: self.mail_service.send_security_alert_email(
                        to_email=user.email,
                        subject="Alerte de sécurité - codes de secours invalides",
                        message="Plusieurs codes de secours invalides ont été saisis sur votre compte super administrateur.",
                        db=None,
                        utilisateur_id=user.id,
                        adresse_ip=adresse_ip,
                        user_agent=user_agent,
                        details={"type": "RECOVERY_CODE_FAILED", "attempts": attempts, "role": role},
                    ),
                    action="RECOVERY_CODE_SUPER_ADMIN_ALERT_EMAIL_EXCEPTION",
                    user=user,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    details={"attempts": attempts, "role": role},
                )
                user.recovery_code_cooldown_until = now + timedelta(minutes=5)
                status_value = "recovery_alert_sent"
                reason = "too_many_recovery_code_failures"
                message = (
                    "Plusieurs codes de secours invalides ont été saisis. Un email d’alerte a été envoyé. Veuillez patienter 5 minutes avant de réessayer."
                    if mail_sent
                    else "Plusieurs codes de secours invalides ont été saisis. L’email d’alerte n’a pas pu être envoyé. Veuillez patienter 5 minutes avant de réessayer."
                )
                remaining_seconds = 300
            elif 6 <= attempts < 10:
                user.recovery_code_cooldown_until = now + timedelta(minutes=5)
                status_value = "cooldown"
                reason = "recovery_code_cooldown_5min"
                message = "Code de secours invalide ou déjà utilisé. Veuillez patienter 5 minutes avant de réessayer."
                remaining_seconds = 300
            elif attempts >= 10:
                mail_sent = self._safe_mail_send(
                    lambda: self._create_super_admin_secure_recovery_link_and_email(
                        user=user,
                        adresse_ip=adresse_ip,
                        user_agent=user_agent,
                        now=now,
                    ),
                    action="RECOVERY_CODE_SECURE_LINK_EMAIL_EXCEPTION",
                    user=user,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    details={"attempts": attempts, "role": role},
                )
                status_value = "secure_link_required"
                reason = "recovery_secure_link_required"
                message = "Connexion sécurisée requise. Trop de codes de secours invalides ont été saisis. Veuillez vérifier votre boîte mail et utiliser le lien sécurisé reçu. Ce lien expire dans 24 heures."
                remaining_seconds = 86400
        elif role in {ROLE_ADMIN, ROLE_USER}:
            if attempts == 3:
                user.recovery_code_cooldown_until = now + timedelta(seconds=30)
                status_value = "cooldown"
                reason = "recovery_code_cooldown_30s"
                message = "Trop de codes de secours invalides. Veuillez patienter 30 secondes avant de réessayer."
                remaining_seconds = 30
            elif attempts == 4:
                user.recovery_code_cooldown_until = now + timedelta(seconds=60)
                status_value = "cooldown"
                reason = "recovery_code_cooldown_60s"
                message = "Trop de codes de secours invalides. Veuillez patienter 60 secondes avant de réessayer."
                remaining_seconds = 60
            elif attempts == 5:
                alert_result = self._send_sensitive_recovery_alerts(
                    user=user,
                    role=role,
                    attempts=attempts,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    now=now,
                )
                mail_sent = bool(alert_result.get("target_mail_sent"))
                supervisor_mail_sent = bool(alert_result.get("supervisor_mail_sent"))
                user.recovery_code_cooldown_until = now + timedelta(minutes=5)
                user.recovery_code_alert_sent_at = now
                user.recovery_code_failed_attempts = attempts
                user.recovery_code_last_failure_at = now
                user.date_modification = now
                status_value = "recovery_alert_sent"
                reason = "too_many_recovery_code_failures"
                message = (
                    "Plusieurs codes de secours invalides ont été saisis. Un email d’alerte a été envoyé. Veuillez patienter 5 minutes avant de réessayer."
                    if mail_sent and supervisor_mail_sent
                    else "Plusieurs codes de secours invalides ont été saisis. Une alerte a été enregistrée. Veuillez patienter 5 minutes avant de réessayer."
                )
                remaining_seconds = 300
            elif 6 <= attempts < 10:
                user.recovery_code_cooldown_until = now + timedelta(minutes=5)
                status_value = "cooldown"
                reason = "recovery_code_cooldown_5min"
                message = "Code de secours invalide ou déjà utilisé. Veuillez patienter 5 minutes avant de réessayer."
                remaining_seconds = 300
            elif attempts >= 10:
                self._disable_account_after_recovery_failures(
                    user=user,
                    role=role,
                    attempts=attempts,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    now=now,
                )
                status_value = "account_disabled"
                reason = "too_many_recovery_code_failures"
                message = (
                    "Votre compte administrateur a été désactivé après plusieurs tentatives de récupération invalides. Veuillez contacter le super administrateur ou demander la réactivation depuis la page de connexion."
                    if role == ROLE_ADMIN
                    else "Votre compte a été désactivé après plusieurs tentatives de récupération invalides. Veuillez contacter l’administrateur de votre département ou demander la réactivation depuis la page de connexion."
                )

        extra = {
            "status": status_value,
            "reason": reason,
            "attempts": attempts,
            "redirect_to": redirect_to,
        }
        if status_value == "account_disabled":
            extra["redirect_to"] = "/account-disabled"
        if remaining_seconds is not None:
            extra["remaining_seconds"] = remaining_seconds
        if mail_sent is not None:
            extra["mail_sent"] = bool(mail_sent)
            extra["email_sent"] = bool(mail_sent)
        if supervisor_mail_sent is not None:
            extra["supervisor_mail_sent"] = bool(supervisor_mail_sent)

        try:
            self.db.add(user)
            self._save_attempt(
                email=user.email,
                user_id=user.id,
                type_tentative="RECOVERY_CODE",
                success=False,
                reason="RECOVERY_CODE_FAILED",
                risk="CRITIQUE" if status_value != "invalid_recovery_code" else "ELEVE",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )
            self._audit(
                action=(
                    "ACCOUNT_DISABLED_AFTER_RECOVERY_FAILURES"
                    if status_value == "account_disabled"
                    else "RECOVERY_CODE_SECURE_LINK_REQUIRED"
                    if status_value == "secure_link_required"
                    else "RECOVERY_CODE_DIRECT_BLOCKED"
                    if status_value == "recovery_code_direct_blocked"
                    else "RECOVERY_CODE_COOLDOWN_5MIN"
                    if status_value == "cooldown" and reason == "recovery_code_cooldown_5min"
                    else "RECOVERY_CODE_COOLDOWN"
                    if status_value in {"recovery_code_cooldown", "cooldown"}
                    else "RECOVERY_CODE_ALERT_SENT"
                    if status_value == "recovery_alert_sent"
                    else "RECOVERY_CODE_FAILED"
                ),
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="CRITIQUE" if status_value != "invalid_recovery_code" else "ELEVE",
                details={"attempt": attempts, "role": role, "reason": reason},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            if status_value == "recovery_alert_sent":
                extra["mail_sent"] = False
                extra["email_sent"] = False
                if supervisor_mail_sent is not None:
                    extra["supervisor_mail_sent"] = False
                message = "Plusieurs codes de secours invalides ont été saisis. Une alerte a été enregistrée. Veuillez patienter 5 minutes avant de réessayer."

        response_code = "ACCOUNT_DISABLED" if status_value == "account_disabled" else "RECOVERY_CODE_INVALID"
        return self._json_error(response_code, message, **extra)

    def _send_sensitive_recovery_alerts(
        self,
        user: Utilisateur,
        role: str,
        attempts: int,
        adresse_ip: str | None,
        user_agent: str | None,
        now,
    ) -> dict:
        account_label = "compte administrateur" if role == ROLE_ADMIN else "compte"
        contact_text = (
            "Si vous n’êtes pas à l’origine de cette action, contactez immédiatement le super administrateur."
            if role == ROLE_ADMIN
            else "Si vous n’êtes pas à l’origine de cette action, contactez immédiatement l’administrateur de votre département."
        )
        supervisor_mail_sent = self._send_recovery_supervisor_action_email(
            user=user,
            role=role,
            attempts=attempts,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        informed_text = (
            "Par sécurité, le super administrateur a été informé."
            if role == ROLE_ADMIN and supervisor_mail_sent
            else "Par sécurité, l’administrateur de votre département a été informé."
            if role == ROLE_USER and supervisor_mail_sent
            else "Une alerte a été enregistrée."
        )

        target_mail_sent = self.mail_service.send_security_alert_email(
            to_email=user.email,
            subject="Alerte de sécurité - codes de secours invalides",
            message=(
                f"Plusieurs tentatives avec des codes de secours invalides ont été détectées sur votre {account_label}.\n\n"
                f"{informed_text}\n\n"
                f"{contact_text}"
            ),
            db=self.db,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={
                "type": "RECOVERY_CODE_ALERT_TARGET",
                "role": role,
                "attempts": attempts,
                "supervisor_mail_sent": bool(supervisor_mail_sent),
            },
        )
        return {
            "target_mail_sent": bool(target_mail_sent),
            "supervisor_mail_sent": bool(supervisor_mail_sent),
        }

    def _send_recovery_supervisor_action_email(
        self,
        user: Utilisateur,
        role: str,
        attempts: int,
        adresse_ip: str | None,
        user_agent: str | None,
    ) -> bool:
        supervisor = self._get_recovery_code_supervisor(user, role)
        if not supervisor:
            try:
                self._audit(
                    action="RECOVERY_SUPERVISOR_LOOKUP",
                    acteur_id=user.id,
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="CRITIQUE",
                    details={"role": role, "found": False, "attempts": attempts},
                )
            except Exception:
                pass
            return False

        departement = user.departement.nom_departement if user.departement else "Non renseigné"
        raw_token = generate_raw_password_reset_token()
        try:
            self._audit(
                action="RECOVERY_SUPERVISOR_LOOKUP",
                acteur_id=user.id,
                cible_id=supervisor.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE",
                details={"role": role, "found": True, "attempts": attempts},
            )
            token_row = JetonReinitialisationMotDePasse(
                utilisateur_id=supervisor.id,
                jeton_hash=hash_token(raw_token),
                type_jeton="RECOVERY_SUPERVISOR_ACTION",
                type_token="RECOVERY_SUPERVISOR_ACTION",
                expire_a=utc_now() + timedelta(minutes=15),
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={
                    "target_user_id": str(user.id),
                    "target_email": user.email,
                    "target_role": role,
                    "target_department": departement,
                    "target_departement_id": str(user.departement_id) if user.departement_id else None,
                    "supervisor_id": str(supervisor.id),
                    "supervisor_email": supervisor.email,
                    "supervisor_role": self._user_role(supervisor),
                    "allowed_actions": ["disable", "regenerate"],
                    "action_allowed": ["disable", "regenerate"],
                    "source": "sensitive_recovery_code_failures",
                    "attempts": attempts,
                },
            )
            self.db.add(token_row)
            self._audit(
                action="RECOVERY_SUPERVISOR_TOKEN_CREATED",
                acteur_id=user.id,
                cible_id=supervisor.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE",
                details={"target_role": role, "attempts": attempts, "expires_in_minutes": 15},
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            try:
                self._audit(
                    action="RECOVERY_SUPERVISOR_TOKEN_CREATE_FAILED",
                    acteur_id=user.id,
                    cible_id=supervisor.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="CRITIQUE",
                    details={"target_role": role, "attempts": attempts, "error": str(exc)},
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
            return False

        base_link = f"{settings.FRONTEND_BASE_URL}/security/recovery-action?token={quote(raw_token, safe='')}"
        disable_link = f"{base_link}&action=disable"
        regenerate_link = f"{base_link}&action=regenerate"

        mail_sent = self.mail_service.send_recovery_supervisor_action_email(
            to_email=supervisor.email,
            target_email=user.email,
            target_role=role,
            department=departement,
            disable_link=disable_link,
            regenerate_link=regenerate_link,
            db=self.db,
            utilisateur_id=supervisor.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={
                "type": "RECOVERY_CODE_SUPERVISOR_ACTION",
                "target_user": user.email,
                "target_role": role,
                "target_department": departement,
                "attempts": attempts,
            },
        )
        self._audit(
            action="RECOVERY_SUPERVISOR_EMAIL_SENT" if mail_sent else "RECOVERY_SUPERVISOR_EMAIL_FAILED",
            acteur_id=user.id,
            cible_id=supervisor.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE" if mail_sent else "CRITIQUE",
            details={"target_role": role, "attempts": attempts, "mail_sent": bool(mail_sent)},
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
        return bool(mail_sent)

    def _notify_recovery_code_supervisor(
        self,
        user: Utilisateur,
        role: str,
        attempts: int,
        adresse_ip: str | None,
        user_agent: str | None,
        disabled: bool = False,
    ) -> bool:
        supervisor = self._get_recovery_code_supervisor(user, role)
        if not supervisor:
            return False

        departement = user.departement.nom_departement if user.departement else "Non renseigné"
        subject = (
            "Compte administrateur désactivé automatiquement"
            if role == ROLE_ADMIN
            else "Compte utilisateur désactivé automatiquement"
        )
        message = (
            "Le compte administrateur suivant a été automatiquement désactivé après plusieurs tentatives de récupération invalides :\n\n"
            if role == ROLE_ADMIN
            else "Le compte utilisateur suivant a été automatiquement désactivé après plusieurs tentatives de récupération invalides :\n\n"
        )
        message += (
            f"Compte : {user.email}\n"
            f"Département : {departement}\n\n"
            + (
                "Vous pouvez le réactiver depuis votre tableau de bord ou depuis une demande de réactivation envoyée par l’administrateur."
                if role == ROLE_ADMIN
                else "Vous pouvez le réactiver depuis votre tableau de bord ou depuis une demande de réactivation envoyée par l’utilisateur."
            )
        )

        return self.mail_service.send_security_alert_email(
            to_email=supervisor.email,
            subject=subject,
            message=message,
            db=self.db,
            utilisateur_id=supervisor.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={
                "type": "ACCOUNT_DISABLED_SUPERVISOR_EMAIL",
                "target_user": user.email,
                "target_role": role,
                "target_department": departement,
                "attempts": attempts,
                "disabled": disabled,
            },
        )

    def _get_recovery_code_supervisor(self, user: Utilisateur, role: str):
        if role == ROLE_ADMIN:
            return (
                self.db.query(Utilisateur)
                .filter(Utilisateur.role == ROLE_SUPER_ADMIN)
                .filter(Utilisateur.est_actif.is_(True))
                .filter(Utilisateur.statut_compte == STATUT_ACTIVE)
                .filter(Utilisateur.date_suppression.is_(None))
                .order_by(Utilisateur.date_creation.asc())
                .first()
            )
        return (
            self.db.query(Utilisateur)
            .filter(Utilisateur.role == ROLE_ADMIN)
            .filter(Utilisateur.departement_id == user.departement_id)
            .filter(Utilisateur.est_actif.is_(True))
            .filter(Utilisateur.statut_compte == STATUT_ACTIVE)
            .filter(Utilisateur.date_suppression.is_(None))
            .order_by(Utilisateur.date_creation.asc())
            .first()
        )

    def _disable_account_after_recovery_failures(
        self,
        user: Utilisateur,
        role: str,
        attempts: int,
        adresse_ip: str | None,
        user_agent: str | None,
        now,
    ) -> None:
        user.est_actif = False
        user.statut_compte = STATUT_BLOQUE_TENTATIVES
        user.date_desactivation = now
        user.date_modification = now
        user.recovery_code_cooldown_until = None
        self.db.query(SessionUtilisateur).filter(
            SessionUtilisateur.utilisateur_id == user.id,
            SessionUtilisateur.revoque_a.is_(None),
        ).update(
            {
                "revoque_a": now,
                "raison_revocation": "Compte désactivé après codes de secours invalides",
                "statut_session": SESSION_REVOKED,
            },
            synchronize_session=False,
        )

        if role == ROLE_ADMIN:
            subject = "Compte administrateur désactivé"
            message = (
                "Votre compte administrateur a été désactivé après plusieurs tentatives de récupération invalides.\n\n"
                "Pour réactiver votre compte, veuillez utiliser le bouton “Demander la réactivation” depuis la page de connexion."
            )
        else:
            subject = "Compte désactivé"
            message = (
                "Votre compte a été désactivé après plusieurs tentatives de récupération invalides.\n\n"
                "Pour réactiver votre compte, veuillez utiliser le bouton “Demander la réactivation” depuis la page de connexion."
            )

        self._safe_mail_send(
            lambda: self.mail_service.send_security_alert_email(
                to_email=user.email,
                subject=subject,
                message=message,
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"type": "ACCOUNT_DISABLED_RECOVERY_CODE_FAILURES", "role": role, "attempts": attempts},
            ),
            action="RECOVERY_CODE_ACCOUNT_DISABLED_EMAIL_EXCEPTION",
            user=user,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"attempts": attempts, "role": role},
        )
        self._safe_mail_send(
            lambda: self._notify_recovery_code_supervisor(
                user=user,
                role=role,
                attempts=attempts,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                disabled=True,
            ),
            action="RECOVERY_CODE_ACCOUNT_DISABLED_SUPERVISOR_EMAIL_EXCEPTION",
            user=user,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"attempts": attempts, "role": role},
        )
        self._audit(
            action="ACCOUNT_DISABLED_AFTER_RECOVERY_FAILURES",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="CRITIQUE",
            details={"role": role, "attempts": attempts},
        )

    def _can_supervisor_manage_recovery_target(
        self,
        supervisor: Utilisateur,
        target: Utilisateur,
    ) -> bool:
        supervisor_role = self._user_role(supervisor)
        target_role = self._user_role(target)
        if supervisor_role == ROLE_SUPER_ADMIN and target_role in {ROLE_ADMIN, ROLE_USER}:
            return True
        if (
            supervisor_role == ROLE_ADMIN
            and target_role == ROLE_USER
            and supervisor.departement_id is not None
            and supervisor.departement_id == target.departement_id
        ):
            return True
        return False

    def _disable_target_from_supervisor_action(
        self,
        target: Utilisateur,
        target_role: str,
        supervisor: Utilisateur,
        adresse_ip: str | None,
        user_agent: str | None,
        now,
    ) -> None:
        target.est_actif = False
        target.statut_compte = STATUT_DISABLED
        target.date_desactivation = now
        target.date_modification = now
        target.recovery_code_cooldown_until = None
        target.recovery_code_alert_sent_at = None
        self.db.query(SessionUtilisateur).filter(
            SessionUtilisateur.utilisateur_id == target.id,
            SessionUtilisateur.revoque_a.is_(None),
        ).update(
            {
                "revoque_a": now,
                "raison_revocation": "Compte désactivé par action superviseur récupération",
                "statut_session": SESSION_REVOKED,
            },
            synchronize_session=False,
        )
        subject = (
            "Compte administrateur désactivé"
            if target_role == ROLE_ADMIN
            else "Compte désactivé"
        )
        message = (
            "Votre compte administrateur a été désactivé par le super administrateur après plusieurs tentatives de récupération invalides."
            if target_role == ROLE_ADMIN
            else "Votre compte a été désactivé par l’administrateur de votre département après plusieurs tentatives de récupération invalides."
        )
        self.db.add(target)
        self._safe_mail_send(
            lambda: self.mail_service.send_security_alert_email(
                to_email=target.email,
                subject=subject,
                message=message,
                db=self.db,
                utilisateur_id=target.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={
                    "type": "RECOVERY_SUPERVISOR_DISABLED_ACCOUNT",
                    "supervisor": supervisor.email,
                },
            ),
            action="RECOVERY_SUPERVISOR_DISABLE_EMAIL_EXCEPTION",
            user=target,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

    def _get_reactivation_supervisor(self, user: Utilisateur, role: str):
        return self._get_recovery_code_supervisor(user, role)

    def _reactivate_disabled_account(self, target: Utilisateur, target_role: str, now) -> None:
        target.est_actif = True
        target.date_desactivation = None
        target.nombre_echecs_password = 0
        target.blocage_password_jusqu_a = None
        target.nombre_echecs_totp = 0
        target.blocage_totp_jusqu_a = None
        target.recovery_code_failed_attempts = 0
        target.recovery_code_last_failure_at = None
        target.recovery_code_cooldown_until = None
        target.recovery_code_alert_sent_at = None
        target.recovery_code_warning_sent_at = None
        target.recovery_secure_link_required = False
        target.recovery_secure_link_expires_at = None
        target.date_modification = now
        target.statut_compte = STATUT_ACTIVE
        self.db.add(target)

    def _send_reactivation_success_email(
        self,
        target: Utilisateur,
        target_role: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ) -> bool:
        return self._safe_mail_send(
            lambda: self.mail_service.send_security_alert_email(
                to_email=target.email,
                subject="Compte administrateur réactivé" if target_role == ROLE_ADMIN else "Compte réactivé",
                message=(
                    "Votre compte administrateur a été réactivé. Vous pouvez vous reconnecter."
                    if target_role == ROLE_ADMIN
                    else "Votre compte a été réactivé. Vous pouvez vous reconnecter."
                ),
                db=self.db,
                utilisateur_id=target.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"type": "ACCOUNT_REACTIVATED_FROM_REQUEST"},
            ),
            action="ACCOUNT_REACTIVATION_SUCCESS_EMAIL_EXCEPTION",
            user=target,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

    def _send_reactivation_ignored_email(
        self,
        target: Utilisateur,
        target_role: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ) -> bool:
        return self._safe_mail_send(
            lambda: self.mail_service.send_security_alert_email(
                to_email=target.email,
                subject="Demande de réactivation non acceptée",
                message=(
                    "Votre demande de réactivation n’a pas été acceptée. Veuillez contacter le super administrateur."
                    if target_role == ROLE_ADMIN
                    else "Votre demande de réactivation n’a pas été acceptée. Veuillez contacter l’administrateur de votre département."
                ),
                db=self.db,
                utilisateur_id=target.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"type": "ACCOUNT_REACTIVATION_IGNORED"},
            ),
            action="ACCOUNT_REACTIVATION_IGNORE_EMAIL_EXCEPTION",
            user=target,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

    def regenerate_recovery_codes_from_link(
        self,
        token: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        token_row = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(token))
            .filter(JetonReinitialisationMotDePasse.type_jeton == "RECOVERY_CODES_REGENERATE")
            .first()
        )
        now = utc_now()
        if not token_row:
            return {"success": False, "status": "invalid", "message": "Ce lien est invalide."}
        if token_row.utilise_a is not None:
            return {
                "success": True,
                "status": "already_used",
                "message": "Ce lien a déjà été utilisé. Les codes de secours ont déjà été régénérés.",
            }
        if ensure_aware_utc(token_row.expire_a) <= now:
            return {
                "success": False,
                "status": "expired",
                "message": "Ce lien n’est plus valide. Veuillez recommencer la procédure de récupération.",
            }

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == token_row.utilisateur_id)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        if not user:
            return {"success": False, "status": "invalid", "message": "Ce lien est invalide."}

        raw_codes = self._replace_user_recovery_codes(user.id)
        token_row.utilise_a = now
        user.recovery_code_failed_attempts = 0
        user.recovery_code_cooldown_until = None
        user.recovery_code_last_failure_at = None
        user.date_modification = now
        self.db.add(token_row)
        self.db.add(user)
        self.mail_service.send_recovery_codes_email(
            to_email=user.email,
            recovery_codes=raw_codes,
            db=None,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            role=self._user_role(user),
            details={"source": "recovery_codes_regenerate_link"},
        )
        self._audit(
            action="RECOVERY_CODES_REGENERATED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"source": "one_shot_link"},
        )
        self.db.commit()
        return {
            "success": True,
            "status": "success",
            "message": "De nouveaux codes de secours ont été générés et envoyés à votre adresse email.",
        }

    def execute_recovery_supervisor_action(
        self,
        token: str,
        action: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        action = str(action or "").lower().strip()
        if action not in {"disable", "regenerate"}:
            return {
                "success": False,
                "status": "forbidden",
                "message": "Action non autorisée.",
            }

        token_row = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(token))
            .filter(
                or_(
                    JetonReinitialisationMotDePasse.type_jeton == "RECOVERY_SUPERVISOR_ACTION",
                    JetonReinitialisationMotDePasse.type_token == "RECOVERY_SUPERVISOR_ACTION",
                )
            )
            .first()
        )
        now = utc_now()
        if not token_row:
            return {
                "success": False,
                "status": "invalid",
                "message": "Ce lien est invalide.",
            }
        if token_row.utilise_a is not None:
            return {
                "success": False,
                "status": "already_used",
                "message": "Ce lien a déjà été utilisé.",
            }
        if ensure_aware_utc(token_row.expire_a) <= now:
            return {
                "success": False,
                "status": "expired",
                "message": "Ce lien d’action a expiré. Veuillez gérer ce compte depuis votre tableau de bord.",
            }

        details = dict(token_row.details or {})
        allowed_actions = details.get("allowed_actions") or details.get("action_allowed") or []
        if action not in set(allowed_actions):
            return {
                "success": False,
                "status": "forbidden",
                "message": "Action non autorisée.",
            }

        supervisor = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == token_row.utilisateur_id)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        target = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == details.get("target_user_id"))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        if not supervisor or not target:
            return {
                "success": False,
                "status": "invalid",
                "message": "Ce lien est invalide.",
            }

        if not self._can_supervisor_manage_recovery_target(supervisor, target):
            return {
                "success": False,
                "status": "forbidden",
                "message": "Action non autorisée.",
            }

        target_role = self._user_role(target)
        if action == "reactivate" and self._account_status(target) not in {STATUT_DISABLED, STATUT_BLOQUE_TENTATIVES}:
            return {
                "success": False,
                "status": "not_reactivable",
                "message": "Ce compte ne peut pas être réactivé par cette action.",
            }
        try:
            if action == "disable":
                self._disable_target_from_supervisor_action(
                    target=target,
                    target_role=target_role,
                    supervisor=supervisor,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    now=now,
                )
                token_row.utilise_a = now
                self.db.add(token_row)
                self._audit(
                    action="RECOVERY_SUPERVISOR_DISABLE_ACCOUNT",
                    acteur_id=supervisor.id,
                    cible_id=target.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="CRITIQUE",
                    details={"target_role": target_role},
                )
                self.db.commit()
                label = "compte administrateur" if target_role == ROLE_ADMIN else "compte"
                return {
                    "success": True,
                    "status": "disabled",
                    "message": f"Le {label} {target.email} a été désactivé avec succès.",
                    "target_email": target.email,
                    "action": action,
                }

            raw_codes = self._replace_user_recovery_codes(target.id)
            target.recovery_code_failed_attempts = 0
            target.recovery_code_cooldown_until = None
            target.recovery_code_last_failure_at = None
            target.recovery_code_alert_sent_at = None
            target.recovery_code_warning_sent_at = None
            target.date_modification = now
            token_row.utilise_a = now
            self.db.add(target)
            self.db.add(token_row)
            mail_sent = self._safe_mail_send(
                lambda: self.mail_service.send_recovery_codes_email(
                    to_email=target.email,
                    recovery_codes=raw_codes,
                    db=self.db,
                    utilisateur_id=target.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    role=target_role,
                    details={"source": "supervisor_recovery_action", "supervisor": supervisor.email},
                ),
                action="RECOVERY_SUPERVISOR_REGENERATE_EMAIL_EXCEPTION",
                user=target,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"supervisor": supervisor.email},
            )
            self._audit(
                action="RECOVERY_SUPERVISOR_REGENERATE_CODES",
                acteur_id=supervisor.id,
                cible_id=target.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE",
                details={"target_role": target_role, "mail_sent": bool(mail_sent)},
            )
            self.db.commit()
            return {
                "success": bool(mail_sent),
                "status": "regenerated" if mail_sent else "mail_failed",
                "message": (
                    f"Les codes de secours du compte {target.email} ont été régénérés et envoyés avec succès."
                    if mail_sent
                    else f"Les codes de secours du compte {target.email} ont été régénérés, mais l’email n’a pas pu être envoyé."
                ),
                "target_email": target.email,
                "mail_sent": bool(mail_sent),
                "action": action,
            }
        except Exception:
            self.db.rollback()
            return {
                "success": False,
                "status": "error",
                "message": "L’action n’a pas pu être exécutée. Veuillez réessayer ou gérer ce compte depuis votre tableau de bord.",
            }

    def request_account_reactivation(
        self,
        email: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        email_clean = str(email or "").strip().lower()
        user = self._get_user_by_email(email_clean)
        if not user:
            return {"success": False, "status": "invalid", "message": "Compte introuvable."}

        role = self._user_role(user)
        account_status = self._account_status(user)
        if account_status not in {STATUT_DISABLED, STATUT_BLOQUE_TENTATIVES}:
            return {"success": False, "status": "not_reactivable", "message": "Ce compte ne peut pas être réactivé par cette action."}
        if role == ROLE_SUPER_ADMIN:
            return {
                "success": False,
                "status": "not_allowed",
                "message": "La demande automatique de réactivation n’est pas disponible pour ce compte.",
            }

        supervisor = self._get_reactivation_supervisor(user, role)
        if not supervisor:
            return {
                "success": False,
                "status": "supervisor_not_found",
                "message": "Aucun responsable actif n’a été trouvé pour traiter cette demande.",
            }

        now = utc_now()
        existing = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.utilisateur_id == supervisor.id)
            .filter(
                or_(
                    JetonReinitialisationMotDePasse.type_jeton == "ACCOUNT_REACTIVATION_REQUEST",
                    JetonReinitialisationMotDePasse.type_token == "ACCOUNT_REACTIVATION_REQUEST",
                )
            )
            .filter(JetonReinitialisationMotDePasse.utilise_a.is_(None))
            .filter(JetonReinitialisationMotDePasse.expire_a > now)
            .all()
        )
        for row in existing:
            if dict(row.details or {}).get("target_user_id") == str(user.id):
                return {
                    "success": True,
                    "status": "already_sent",
                    "message": (
                        "Une demande de réactivation a déjà été envoyée. Veuillez attendre le traitement par le super administrateur."
                        if role == ROLE_ADMIN
                        else "Une demande de réactivation a déjà été envoyée. Veuillez attendre le traitement par votre administrateur."
                    ),
                }

        raw_token = generate_raw_password_reset_token()
        department = user.departement.nom_departement if user.departement else "Non renseigné"
        self.db.add(
            JetonReinitialisationMotDePasse(
                utilisateur_id=supervisor.id,
                jeton_hash=hash_token(raw_token),
                type_jeton="ACCOUNT_REACTIVATION_REQUEST",
                type_token="ACCOUNT_REACTIVATION_REQUEST",
                expire_a=now + timedelta(hours=24),
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={
                    "target_user_id": str(user.id),
                    "target_email": user.email,
                    "target_role": role,
                    "target_department": department,
                    "supervisor_id": str(supervisor.id),
                    "supervisor_role": self._user_role(supervisor),
                    "allowed_actions": ["reactivate", "ignore"],
                    "source": "disabled_account_login_request",
                },
            )
        )
        self._audit(
            action="ACCOUNT_REACTIVATION_REQUESTED",
            acteur_id=user.id,
            cible_id=supervisor.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE",
            details={"target_role": role, "supervisor_role": self._user_role(supervisor)},
        )
        self.db.commit()

        base_link = f"{settings.FRONTEND_BASE_URL}/security/reactivation-action?token={quote(raw_token, safe='')}"
        mail_sent = self._safe_mail_send(
            lambda: self.mail_service.send_account_reactivation_request_email(
                to_email=supervisor.email,
                target_email=user.email,
                target_role=role,
                department=department,
                reactivate_link=f"{base_link}&action=reactivate",
                ignore_link=f"{base_link}&action=ignore",
                db=self.db,
                utilisateur_id=supervisor.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"target_user": user.email, "target_role": role},
            ),
            action="ACCOUNT_REACTIVATION_REQUEST_EMAIL_EXCEPTION",
            user=user,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
        return {
            "success": True,
            "status": "sent",
            "message": (
                "Votre demande de réactivation a été envoyée au super administrateur."
                if role == ROLE_ADMIN
                else "Votre demande de réactivation a été envoyée à l’administrateur de votre département."
            ),
            "mail_sent": bool(mail_sent),
        }

    def execute_account_reactivation_action(
        self,
        token: str,
        action: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        action = str(action or "").lower().strip()
        if action not in {"reactivate", "ignore"}:
            return {"success": False, "status": "forbidden", "message": "Action non autorisée."}

        token_row = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(token))
            .filter(
                or_(
                    JetonReinitialisationMotDePasse.type_jeton == "ACCOUNT_REACTIVATION_REQUEST",
                    JetonReinitialisationMotDePasse.type_token == "ACCOUNT_REACTIVATION_REQUEST",
                )
            )
            .first()
        )
        now = utc_now()
        if not token_row:
            return {"success": False, "status": "invalid", "message": "Ce lien est invalide."}
        if token_row.utilise_a is not None:
            return {"success": False, "status": "already_used", "message": "Ce lien a déjà été utilisé."}
        if ensure_aware_utc(token_row.expire_a) <= now:
            return {"success": False, "status": "expired", "message": "Ce lien de réactivation a expiré."}

        details = dict(token_row.details or {})
        if action not in set(details.get("allowed_actions") or []):
            return {"success": False, "status": "forbidden", "message": "Action non autorisée."}

        supervisor = self.db.query(Utilisateur).filter(Utilisateur.id == token_row.utilisateur_id).first()
        target = self.db.query(Utilisateur).filter(Utilisateur.id == details.get("target_user_id")).first()
        if not supervisor or not target or not self._can_supervisor_manage_recovery_target(supervisor, target):
            return {"success": False, "status": "forbidden", "message": "Action non autorisée."}

        target_role = self._user_role(target)
        try:
            token_row.utilise_a = now
            if action == "ignore":
                self._send_reactivation_ignored_email(target, target_role, adresse_ip, user_agent)
                self.db.add(token_row)
                self._audit(
                    action="ACCOUNT_REACTIVATION_IGNORED",
                    acteur_id=supervisor.id,
                    cible_id=target.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="ELEVE",
                    details={"target_role": target_role},
                )
                self.db.commit()
                return {"success": True, "status": "ignored", "message": "La demande de réactivation a été ignorée."}

            self._reactivate_disabled_account(target, target_role, now)
            self.db.add(token_row)
            self._send_reactivation_success_email(target, target_role, adresse_ip, user_agent)
            self._audit(
                action="ACCOUNT_REACTIVATION_APPROVED",
                acteur_id=supervisor.id,
                cible_id=target.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE",
                details={"target_role": target_role},
            )
            self.db.commit()
            label = "compte administrateur" if target_role == ROLE_ADMIN else "compte"
            return {
                "success": True,
                "status": "reactivated",
                "message": f"Le {label} {target.email} a été réactivé avec succès.",
            }
        except Exception:
            self.db.rollback()
            return {"success": False, "status": "error", "message": "L’action n’a pas pu être exécutée. Veuillez réessayer."}

    def _replace_user_recovery_codes(self, user_id) -> list[str]:
        now = utc_now()
        self.db.query(CodeSecours).filter(CodeSecours.utilisateur_id == user_id).update(
            {
                "utilise": True,
                "est_utilise": True,
                "utilise_a": now,
                "date_expiration": now,
            },
            synchronize_session=False,
        )
        raw_codes = [self._generate_recovery_code() for _ in range(10)]
        for raw_code in raw_codes:
            self.db.add(
                CodeSecours(
                    utilisateur_id=user_id,
                    code_hash=hash_recovery_code(raw_code),
                    utilise=False,
                    est_utilise=False,
                    date_creation=now,
                    date_expiration=None,
                )
            )
        self.db.flush()
        return raw_codes

    def _has_valid_mfa_recovery_links(self, user: Utilisateur, now) -> bool:
        valid_count = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.utilisateur_id == user.id)
            .filter(JetonReinitialisationMotDePasse.type_jeton.in_(["MFA_BACKUP_CODE", "MFA_RESET"]))
            .filter(JetonReinitialisationMotDePasse.utilise_a.is_(None))
            .filter(JetonReinitialisationMotDePasse.expire_a > now)
            .count()
        )
        return valid_count >= 2

    def _mfa_recovery_required_response_if_active(
        self,
        user: Utilisateur,
        role: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        if int(user.nombre_echecs_totp or 0) < 4:
            return None

        now = utc_now()
        remaining_seconds = self._remaining_seconds(user.blocage_totp_jusqu_a)
        mail_sent = False
        message = "Vérification MFA bloquée. Veuillez vérifier votre boîte mail."

        links_still_valid = self._has_valid_mfa_recovery_links(user, now)
        if remaining_seconds <= 0 or not links_still_valid:
            user.blocage_totp_jusqu_a = now + timedelta(minutes=15)
            user.date_modification = now
            backup_link, reset_link = self._create_admin_mfa_recovery_links(
                user=user,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                now=now,
            )
            mail_sent = self.mail_service.send_admin_mfa_blocked_email(
                to_email=user.email,
                backup_code_link=backup_link,
                mfa_reset_link=reset_link,
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                role=role,
            )
            remaining_seconds = 900
            message = (
                "Vérification MFA bloquée. Un nouveau mail de récupération a été envoyé."
                if mail_sent
                else "Vérification MFA bloquée. Veuillez vérifier votre boîte mail."
            )
            self._audit(
                action="MFA_BLOCKED_EMAIL_RESENT" if mail_sent else "MFA_BLOCKED_EMAIL_RESEND_FAILED",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="ELEVE" if mail_sent else "CRITIQUE",
                details={"role": role, "reason": "mfa_recovery_required"},
            )

        self.db.add(user)
        return self._json_error(
            "MFA_TEMPORARILY_LOCKED",
            message,
            status="recovery_required",
            reason="mfa_blocked",
            role=role,
            mail_sent=bool(mail_sent),
            can_use_backup_code=True,
            can_reset_mfa=True,
            remaining_seconds=remaining_seconds,
            redirect_to="/mfa-blocked",
        )

    def _secure_link_required_response_if_active(self, user: Utilisateur, role: str):
        if role != ROLE_SUPER_ADMIN or not getattr(user, "recovery_secure_link_required", False):
            return None

        now = utc_now()
        expires_at = ensure_aware_utc(user.recovery_secure_link_expires_at)
        if expires_at and expires_at <= now:
            user.recovery_secure_link_required = False
            user.recovery_secure_link_expires_at = None
            user.recovery_code_failed_attempts = 0
            user.recovery_code_cooldown_until = None
            user.date_modification = now
            self.db.add(user)
            self._audit(
                action="RECOVERY_CODE_SECURE_LINK_EXPIRED",
                acteur_id=user.id,
                cible_id=user.id,
                niveau_risque="MOYEN",
                details={"reason": "secure_recovery_link_expired"},
            )
            return self._json_error(
                "SECURE_LINK_EXPIRED",
                "Le lien sécurisé a expiré. Vous pouvez vous connecter normalement depuis votre plateforme.",
                status="secure_link_expired",
                reason="secure_recovery_link_expired",
                redirect_to="/login",
            )

        return self._json_error(
            "SECURE_LINK_REQUIRED",
            "Connexion impossible. Veuillez vérifier votre boîte mail. Le lien sécurisé reçu par email est l’unique moyen de connexion pendant cette période.",
            status="secure_link_required",
            reason="recovery_secure_link_required",
            expires_in_seconds=self._remaining_seconds(expires_at),
            redirect_to="/secure-recovery",
        )

    def _create_super_admin_secure_recovery_link_and_email(
        self,
        user: Utilisateur,
        adresse_ip: str | None,
        user_agent: str | None,
        now,
    ) -> bool:
        raw_token = generate_raw_password_reset_token()
        expires_at = now + timedelta(hours=24)
        token_type = "SUPER_ADMIN_SECURE_RECOVERY_24H"

        self.db.add(
            JetonReinitialisationMotDePasse(
                utilisateur_id=user.id,
                jeton_hash=hash_token(raw_token),
                type_jeton=token_type,
                type_token=token_type,
                expire_a=expires_at,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={"role": ROLE_SUPER_ADMIN, "source": "recovery_code_failures"},
            )
        )
        user.recovery_secure_link_required = True
        user.recovery_secure_link_expires_at = expires_at
        user.date_modification = now
        self.db.add(user)
        self.db.flush()

        secure_link = f"{settings.FRONTEND_BASE_URL}/secure-recovery?token={quote(raw_token, safe='')}"
        mail_sent = self.mail_service.send_secure_recovery_required_email(
            to_email=user.email,
            secure_link=secure_link,
            db=None,
            utilisateur_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )
        self._audit(
            action="RECOVERY_CODE_SECURE_LINK_REQUIRED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="CRITIQUE",
            details={"mail_sent": bool(mail_sent)},
        )
        return bool(mail_sent)

    def complete_super_admin_secure_recovery(
        self,
        token: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        token_row = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(token))
            .filter(JetonReinitialisationMotDePasse.type_jeton == "SUPER_ADMIN_SECURE_RECOVERY_24H")
            .first()
        )
        now = utc_now()
        if not token_row:
            return self._json_error(
                "SECURE_LINK_INVALID",
                "Ce lien sécurisé est invalide.",
                status="secure_link_invalidated",
                reason="secure_recovery_link_invalid",
                redirect_to="/login",
            )

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == token_row.utilisateur_id)
            .filter(Utilisateur.role == ROLE_SUPER_ADMIN)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        if not user:
            return self._json_error(
                "ACCOUNT_NOT_FOUND",
                "Compte introuvable.",
                status="secure_link_invalidated",
                redirect_to="/login",
            )

        if token_row.utilise_a is not None:
            return self._json_error(
                "SECURE_LINK_USED",
                "Ce lien n’est plus valide.",
                status="token_used",
                reason="secure_recovery_link_used",
                redirect_to="/login",
            )

        if ensure_aware_utc(token_row.expire_a) <= now:
            user.recovery_secure_link_required = False
            user.recovery_secure_link_expires_at = None
            user.date_modification = now
            self.db.add(user)
            self._audit(
                action="RECOVERY_CODE_SECURE_LINK_EXPIRED",
                acteur_id=user.id,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="MOYEN",
            )
            self.db.commit()
            return self._json_error(
                "SECURE_LINK_EXPIRED",
                "Ce lien sécurisé a expiré. Veuillez vous connecter normalement depuis votre plateforme.",
                status="secure_link_expired",
                reason="secure_recovery_link_expired",
                redirect_to="/login",
            )

        token_row.utilise_a = now
        user.recovery_secure_link_required = False
        user.recovery_secure_link_expires_at = None
        user.recovery_code_failed_attempts = 0
        user.recovery_code_cooldown_until = None
        user.nombre_echecs_totp = 0
        user.blocage_totp_jusqu_a = None
        user.date_derniere_connexion = now
        user.date_modification = now
        self.db.add(token_row)
        self.db.add(user)

        access_token = self._create_final_session(
            user=user,
            role=ROLE_SUPER_ADMIN,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            methode_mfa="SECURE_RECOVERY_LINK",
        )
        self._audit(
            action="RECOVERY_CODE_SECURE_LINK_USED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
        )
        self.db.commit()
        return {
            "success": True,
            "code": "SECURE_RECOVERY_SUCCESS",
            "status": "success",
            "message": "Connexion sécurisée validée.",
            "access_token": access_token,
            "token_type": "bearer",
            "role": ROLE_SUPER_ADMIN,
            "user": {"email": user.email, "role": ROLE_SUPER_ADMIN},
            "redirect_to": self._dashboard_path(ROLE_SUPER_ADMIN),
        }

    def _create_final_session(
        self,
        user: Utilisateur,
        role: str,
        adresse_ip: str | None,
        user_agent: str | None,
        methode_mfa: str | None = None,
    ) -> str:
        raw_session_token = generate_raw_session_token()
        now = utc_now()

        session = SessionUtilisateur(
            utilisateur_id=user.id,
            jeton_session_hash=hash_session_token(raw_session_token),
            role=role,
            statut_session=SESSION_ACTIVE,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            methode_mfa=methode_mfa,
            date_creation=now,
            derniere_activite_a=now,
            expire_a=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

        self.db.add(session)
        self.db.flush()

        self._audit(
            action=AUDIT_SESSION_CREATED,
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="FAIBLE",
            details={"role": role},
        )

        return create_access_token(
            data={
                "sub": str(user.id),
                "session_token": raw_session_token,
                "role": role,
            },
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

    def _revoke_user_sessions_on_security_lock(self, user: Utilisateur) -> None:
        now = utc_now()

        self.db.query(SessionUtilisateur).filter(
            SessionUtilisateur.utilisateur_id == user.id,
            SessionUtilisateur.revoque_a.is_(None),
        ).update(
            {
                "revoque_a": now,
                "raison_revocation": "Blocage sécurité après tentatives échouées",
                "statut_session": SESSION_REVOKED,
            },
            synchronize_session=False,
        )

        self._audit(
            action="SECURITY_LOCKOUT_SESSIONS_REVOKED",
            acteur_id=user.id,
            cible_id=user.id,
            niveau_risque="ELEVE",
            details={"reason": "password_lockout"},
        )

    def _create_admin_mfa_recovery_links(
        self,
        user: Utilisateur,
        adresse_ip: str | None,
        user_agent: str | None,
        now,
    ) -> tuple[str, str]:
        role = self._user_role(user)
        links = {}
        for token_type, route in (
            ("MFA_BACKUP_CODE", "/mfa/recovery-code"),
            ("MFA_RESET", "/mfa/reset"),
        ):
            raw_token = generate_raw_password_reset_token()
            self.db.add(
                JetonReinitialisationMotDePasse(
                    utilisateur_id=user.id,
                    jeton_hash=hash_token(raw_token),
                    type_jeton=token_type,
                    type_token=token_type,
                    expire_a=now + timedelta(minutes=15),
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    details={"role": role, "source": "admin_login_mfa_blocked"},
                )
            )
            links[token_type] = (
                f"{settings.FRONTEND_BASE_URL}{route}"
                f"?token={quote(raw_token, safe='')}&role={quote(role, safe='')}"
            )
        self.db.flush()
        return links["MFA_BACKUP_CODE"], links["MFA_RESET"]

    def _get_admin_mfa_reset_token(self, token: str):
        token_row = (
            self.db.query(JetonReinitialisationMotDePasse)
            .filter(JetonReinitialisationMotDePasse.jeton_hash == hash_token(token))
            .filter(JetonReinitialisationMotDePasse.type_jeton == "MFA_RESET")
            .first()
        )
        now = utc_now()
        if not token_row or token_row.utilise_a is not None:
            return None, None, self._json_error(
                "MFA_RESET_LINK_INVALID",
                "Lien invalide ou expiré.",
                status="invalid_or_expired_token",
                redirect_to="/login",
            )
        if ensure_aware_utc(token_row.expire_a) <= now:
            existing_valid_link = (
                self.db.query(JetonReinitialisationMotDePasse)
                .filter(JetonReinitialisationMotDePasse.utilisateur_id == token_row.utilisateur_id)
                .filter(JetonReinitialisationMotDePasse.type_jeton == "MFA_RESET")
                .filter(JetonReinitialisationMotDePasse.utilise_a.is_(None))
                .filter(JetonReinitialisationMotDePasse.expire_a > now)
                .first()
            )
            if existing_valid_link:
                return None, None, self._json_error(
                    "MFA_RESET_LINK_ALREADY_SENT",
                    "Un lien vient déjà d’être envoyé. Veuillez vérifier votre boîte mail.",
                    status="link_already_sent",
                    redirect_to="/mfa/reset",
                )
            return None, None, self._json_error(
                "MFA_RESET_LINK_EXPIRED",
                "Lien expiré. Veuillez recommencer la connexion pour recevoir un nouveau lien.",
                status="token_expired",
                redirect_to="/login",
            )

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == token_row.utilisateur_id)
            .filter(Utilisateur.role.in_([ROLE_USER, ROLE_ADMIN, ROLE_SUPER_ADMIN]))
            .filter(Utilisateur.est_actif.is_(True))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        if not user:
            return None, None, self._json_error(
                "ACCOUNT_NOT_FOUND",
                "Compte introuvable.",
                status="invalid_or_expired_token",
                redirect_to="/login",
            )
        return token_row, user, None

    def _handle_admin_mfa_reset_recovery_failure(
        self,
        token_row: JetonReinitialisationMotDePasse,
        user: Utilisateur,
        adresse_ip: str | None,
        user_agent: str | None,
        now,
    ):
        new_count = int(token_row.mfa_echecs_recovery or 0) + 1
        token_row.mfa_echecs_recovery = new_count
        token_row.mfa_dernier_echec_a = now

        status_value = "invalid_recovery_code"
        reason = "mfa_reset_recovery_invalid"
        message = "Code de secours invalide ou déjà utilisé."
        remaining_seconds = None
        mail_sent = None

        if new_count == 3:
            token_row.mfa_recovery_bloque_jusqu_a = now + timedelta(seconds=30)
            status_value = "recovery_cooldown"
            reason = "recovery_code_cooldown_30s"
            message = "Plusieurs codes incorrects. Veuillez patienter 30 secondes."
            remaining_seconds = 30
        elif new_count >= 4:
            token_row.mfa_recovery_bloque_jusqu_a = now + timedelta(minutes=5)
            status_value = "recovery_blocked"
            reason = "too_many_backup_code_failures"
            message = "Récupération temporairement bloquée. Veuillez vérifier votre boîte mail."
            remaining_seconds = 300
            mail_sent = self.mail_service.send_recovery_blocked_email(
                to_email=user.email,
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                role=self._user_role(user),
            )

        self.db.add(token_row)
        self._audit(
            action=(
                "MFA_RESET_RECOVERY_CODE_BLOCKED"
                if status_value == "recovery_blocked"
                else "MFA_RESET_RECOVERY_CODE_FAILURE"
            ),
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="CRITIQUE" if status_value == "recovery_blocked" else "ELEVE",
            details={"attempt": new_count, "reason": reason},
        )
        self.db.commit()

        extra = {
            "status": status_value,
            "reason": reason,
            "attempts": new_count,
            "redirect_to": "/mfa/reset",
        }
        if remaining_seconds is not None:
            extra["remaining_seconds"] = remaining_seconds
        if mail_sent is not None:
            extra["mail_sent"] = bool(mail_sent)

        return self._json_error("MFA_RESET_RECOVERY_FAILED", message, **extra)

    def _make_qr_base64(self, data: str) -> str:
        img = qrcode.make(data)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _generate_recovery_code(self) -> str:
        return pyotp.random_base32()[:10]

    def _create_lockout_reset_token_and_email(
        self,
        user: Utilisateur,
        role: str,
        adresse_ip: str | None,
        user_agent: str | None,
        now=None,
    ) -> bool:
        now = now or utc_now()

        raw_token = generate_raw_password_reset_token()

        token = JetonReinitialisationMotDePasse(
            utilisateur_id=user.id,
            jeton_hash=hash_token(raw_token),
            type_jeton=TOKEN_PASSWORD_RESET_FROM_LOCKOUT,
            type_token=TOKEN_PASSWORD_RESET_FROM_LOCKOUT,
            expire_a=now + timedelta(minutes=15),
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"role": role, "source": "password_lockout"},
        )

        self.db.add(token)
        self.db.flush()

        reset_path = (
            "/password-reset/from-lockout" if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN} else "/password-reset"
        )
        reset_link = (
            f"{settings.FRONTEND_BASE_URL}{reset_path}?token={quote(raw_token, safe='')}"
        )

        detected_at = self.mail_service.format_datetime_for_email(now)
        ip_value = adresse_ip or "Non disponible"
        user_agent_value = self.mail_service.format_user_agent(user_agent)
        incident_id = str(uuid4())

        raw_report_token = generate_raw_password_reset_token()
        report_token_row = JetonReinitialisationMotDePasse(
            utilisateur_id=user.id,
            jeton_hash=hash_token(raw_report_token),
            type_jeton="SECURITY_REPORT",
            type_token="SECURITY_REPORT",
            expire_a=now + timedelta(hours=24),
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={
                "role": role,
                "incident_id": incident_id,
                "source_ip": ip_value,
                "source_user_agent": user_agent_value,
                "detected_at": detected_at,
            },
        )
        self.db.add(report_token_row)
        self.db.flush()
        report_link = (
            f"{settings.FRONTEND_BASE_URL}/security/report"
            f"?token={quote(raw_report_token, safe='')}"
        )

        if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
            mail_sent = self.mail_service.send_admin_password_lockout_email(
                to_email=user.email,
                reset_link=reset_link,
                report_link=report_link,
                ip_address=ip_value,
                user_agent_value=user_agent_value,
                detected_at=detected_at,
                reset_link_expire_minutes=15,
                report_link_expire_hours=24,
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )
        else:
            mail_sent = self.mail_service.send_lockout_security_email(
                to_email=user.email,
                reset_link=reset_link,
                report_link=report_link,
                ip_address=ip_value,
                user_agent_value=user_agent_value,
                detected_at=detected_at,
                reset_link_expire_minutes=15,
                report_link_expire_hours=24,
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

        self._audit(
            action="PASSWORD_LOCKOUT_SECURITY_EMAIL_SENT" if mail_sent else "PASSWORD_LOCKOUT_SECURITY_EMAIL_FAILED",
            acteur_id=user.id,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="ELEVE" if mail_sent else "CRITIQUE",
            details={
                "role": role,
                "incident_id": incident_id,
                "reset_link_debug": reset_link if settings.MAIL_DEBUG_MODE else None,
                "report_link_debug": report_link if settings.MAIL_DEBUG_MODE else None,
            },
        )
        return bool(mail_sent)

    def _should_send_security_email(self, user: Utilisateur, now) -> bool:
        last_alert = ensure_aware_utc(user.date_derniere_alerte_securite)
        if not last_alert:
            return True
        return last_alert + timedelta(minutes=self.SECURITY_EMAIL_COOLDOWN_MINUTES) <= now

    def _has_unresolved_reported_incident(self, user: Utilisateur) -> bool:
        latest_incident = (
            self.db.query(JournalAudit)
            .filter(JournalAudit.cible_utilisateur_id == user.id)
            .filter(JournalAudit.action_effectuee == "SECURITY_INCIDENT_REPORTED")
            .order_by(JournalAudit.date_action.desc())
            .first()
        )

        if not latest_incident:
            return False

        incident_date = ensure_aware_utc(latest_incident.date_action)
        last_login = ensure_aware_utc(user.date_derniere_connexion)
        last_password_change = ensure_aware_utc(user.date_dernier_changement_mot_de_passe)

        if last_password_change and last_password_change >= incident_date:
            return False

        if last_login and last_login >= incident_date:
            return False

        return True

    def _get_user_by_email(self, email: str) -> Utilisateur | None:
        return (
            self.db.query(Utilisateur)
            .filter(Utilisateur.email == email)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

    def _get_active_totp(self, user_id) -> IdentifiantTotp | None:
        return (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user_id)
            .filter(IdentifiantTotp.est_actif.is_(True))
            .filter(IdentifiantTotp.date_revocation.is_(None))
            .first()
        )

    def _user_role(self, user: Utilisateur) -> str:
        role = str(user.role or ROLE_USER).upper()
        if role in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
            return role
        return ROLE_USER

    def _account_status(self, user: Utilisateur) -> str:
        if user.date_suppression is not None:
            return STATUT_SUPPRIME
        raw = str(user.statut_compte or "").upper()
        if raw in {"ACTIVE", STATUT_ACTIVE} and user.est_actif:
            return STATUT_ACTIVE
        if raw in {"PENDING_ACTIVATION", "MFA_SETUP_REQUIRED", STATUT_PENDING_ACTIVATION}:
            return STATUT_PENDING_ACTIVATION
        if raw in {"DISABLED", STATUT_DISABLED}:
            return STATUT_DISABLED
        if raw == STATUT_BLOQUE_TENTATIVES:
            return STATUT_BLOQUE_TENTATIVES
        return raw or STATUT_DISABLED

    def _inactive_account_error(self, user: Utilisateur, role: str, redirect_to: str = "/account-disabled"):
        account_status = self._account_status(user)
        messages = {
            STATUT_DISABLED: "Votre compte a été désactivé. Contactez un administrateur.",
            STATUT_BLOQUE_TENTATIVES: "Votre compte est bloqué après plusieurs tentatives de connexion. Contactez un administrateur.",
            STATUT_PENDING_ACTIVATION: "Votre compte est en attente de première connexion.",
            STATUT_SUPPRIME: "Ce compte n’est plus disponible.",
        }
        reason_by_status = {
            STATUT_DISABLED: "account_disabled",
            STATUT_BLOQUE_TENTATIVES: "account_blocked",
            STATUT_PENDING_ACTIVATION: "account_pending_first_login",
            STATUT_SUPPRIME: "account_deleted",
        }
        return self._json_error(
            "ACCOUNT_UNAVAILABLE",
            messages.get(account_status, "Compte indisponible."),
            status=reason_by_status.get(account_status, "account_unavailable"),
            reason=reason_by_status.get(account_status, "account_unavailable"),
            role=role,
            email=user.email,
            statut_compte=account_status,
            can_request_reactivation=account_status in {STATUT_DISABLED, STATUT_BLOQUE_TENTATIVES}
            and role in {ROLE_USER, ROLE_ADMIN},
            redirect_to=redirect_to,
        )

    def _dashboard_path(self, role: str) -> str:
        role = str(role or ROLE_USER).upper()
        if role in {ROLE_SUPER_ADMIN, ROLE_ADMIN}:
            return "/accueil"
        return "/user/dashboard"

    def _is_admin(self, user: Utilisateur) -> bool:
        return self._user_role(user) in {ROLE_ADMIN, ROLE_SUPER_ADMIN}

    def _create_super_admin_mfa_setup_token(self, user: Utilisateur) -> str:
        role = self._user_role(user)
        return create_scoped_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": role,
                "setup_id": str(uuid4()),
            },
            purpose="super_admin_mfa_setup",
            expires_delta=timedelta(minutes=10),
        )

    def _create_activation_totp_setup_token(self, user: Utilisateur) -> str:
        return create_scoped_token(
            data={"sub": str(user.id), "email": user.email},
            purpose="totp_setup",
            expires_delta=timedelta(minutes=10),
        )

    def _decode_super_admin_mfa_setup_token(self, setup_token: str):
        try:
            payload = decode_scoped_token(setup_token, "super_admin_mfa_setup")
        except Exception:
            return None, None, self._json_error(
                "MFA_SETUP_TOKEN_INVALID",
                "Session de configuration MFA expirée. Veuillez vous reconnecter.",
                status="token_expired",
                redirect_to="/login",
            )

        user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == payload.get("sub"))
            .filter(Utilisateur.email == str(payload.get("email", "")).lower())
            .filter(Utilisateur.est_actif.is_(True))
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )
        if not user or user.statut_compte != STATUT_ACTIVE:
            return payload, None, self._json_error(
                "MFA_SETUP_ACCOUNT_INVALID",
                "Compte indisponible.",
                status="invalid_token",
                redirect_to="/login",
            )
        return payload, user, None

    def _is_locked(self, until_value) -> bool:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return False
        return until_value > utc_now()

    def _remaining_seconds(self, until_value) -> int:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return 0
        return max(0, int((until_value - utc_now()).total_seconds()))

    def _format_remaining(self, until_value) -> str:
        until_value = ensure_aware_utc(until_value)
        if not until_value:
            return "00:00"

        seconds = max(0, int((until_value - utc_now()).total_seconds()))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _json_error(self, code: str, message: str, **extra):
        data = {
            "success": False,
            "code": code,
            "message": message,
        }
        data.update(extra)
        return data

    def _safe_mail_send(
        self,
        sender,
        action: str,
        user: Utilisateur | None = None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> bool:
        try:
            return bool(sender())
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def _save_attempt(
        self,
        email: str,
        user_id,
        type_tentative: str,
        success: bool,
        reason: Optional[str],
        risk: str,
        adresse_ip: Optional[str],
        user_agent: Optional[str],
    ) -> None:
        self.db.add(
            TentativeConnexion(
                utilisateur_id=user_id,
                email_saisi=email,
                type_tentative=type_tentative,
                succes=success,
                raison_echec=reason,
                niveau_risque=risk,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details={},
            )
        )
        self.db.flush()

    def _audit(
        self,
        action: str,
        acteur_id=None,
        cible_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        niveau_risque: str = "FAIBLE",
        details: dict | None = None,
    ) -> None:
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


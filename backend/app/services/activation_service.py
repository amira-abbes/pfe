import base64
from datetime import timedelta
from io import BytesIO

import pyotp
import qrcode
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.constants import (
    AUDIT_ACCOUNT_ACTIVATED,
    AUDIT_ACCOUNT_ACTIVATION_STARTED,
    AUDIT_ACTIVATION_LINK_INVALID,
    AUDIT_PASSWORD_CREATED,
    AUDIT_TOTP_SETUP_FAILED,
    AUDIT_TOTP_SETUP_STARTED,
    AUDIT_TOTP_SETUP_SUCCESS,
    RISK_MEDIUM,
    STATUT_ACTIVE,
    STATUT_MFA_SETUP_REQUIRED,
    STATUT_PENDING_ACTIVATION,
    TOKEN_ACCOUNT_ACTIVATION,
)
from app.core.security import (
    create_scoped_token,
    decode_scoped_token,
    decrypt_secret,
    encrypt_secret,
    ensure_aware_utc,
    generate_numeric_code,
    generate_secure_token,
    hash_activation_token,
    hash_password,
    hash_recovery_code,
    utc_now,
)
from app.models.code_secours import CodeSecours
from app.models.identifiant_totp import IdentifiantTotp
from app.models.jeton_activation import JetonActivation
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur
from app.services.mail_service import MailService
from app.services.password_policy_service import PasswordPolicyService


class ActivationService:
    def __init__(self, db: Session):
        self.db = db
        self.password_policy = PasswordPolicyService()
        self.mail_service = MailService()

    def verify_activation_token(
        self,
        token: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        activation = self._get_activation_by_raw_token(token)

        if not activation or not activation.utilisateur:
            self._audit(
                action=AUDIT_ACTIVATION_LINK_INVALID,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=RISK_MEDIUM,
                details={"reason": "token_not_found"},
            )
            self.db.commit()
            return self._activation_invalid_response()

        user = activation.utilisateur
        invalid_reason = self._activation_invalid_reason(activation, user)

        if invalid_reason:
            self._audit(
                action=AUDIT_ACTIVATION_LINK_INVALID,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=RISK_MEDIUM,
                details={"reason": invalid_reason},
            )
            self.db.commit()

            return self._activation_invalid_response(
                code="ACTIVATION_LINK_EXPIRED"
                if invalid_reason == "token_expired"
                else "ACTIVATION_LINK_INVALID"
            )

        self._audit(
            action=AUDIT_ACCOUNT_ACTIVATION_STARTED,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="FAIBLE",
        )
        self.db.commit()

        return {
            "success": True,
            "code": "ACTIVATION_LINK_VALID",
            "message": "Lien d’activation valide. Veuillez créer votre mot de passe.",
            "email": user.email,
        }

    def resend_activation_link(
        self,
        email: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        generic_response = {
            "success": True,
            "code": "ACTIVATION_RESEND_ACCEPTED",
            "message": (
                "Si ce compte existe et est encore en attente d’activation, "
                "un nouveau lien d’activation a été envoyé."
            ),
        }

        email_clean = str(email or "").strip().lower()

        try:
            user = (
                self.db.query(Utilisateur)
                .filter(Utilisateur.email == email_clean)
                .filter(Utilisateur.date_suppression.is_(None))
                .first()
            )

            if not user:
                self._audit(
                    action="ACTIVATION_RESEND_UNKNOWN_EMAIL",
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="MOYEN",
                    details={"email": email_clean},
                )
                self.db.commit()
                return generic_response

            if not user.est_actif:
                self._audit(
                    action="ACTIVATION_RESEND_DISABLED_ACCOUNT",
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="MOYEN",
                    details={"email": email_clean},
                )
                self.db.commit()
                return {
                    "success": False,
                    "code": "ACCOUNT_DISABLED",
                    "message": "Ce compte est désactivé. Veuillez contacter l’administrateur.",
                }

            if user.statut_compte == STATUT_ACTIVE:
                self._audit(
                    action="ACTIVATION_RESEND_ALREADY_ACTIVE",
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="FAIBLE",
                    details={"email": email_clean},
                )
                self.db.commit()
                return {
                    "success": False,
                    "code": "ACCOUNT_ALREADY_ACTIVE",
                    "message": (
                        "Compte déjà activé. Si vous rencontrez un problème, "
                        "réinitialisez votre mot de passe ou contactez l’administrateur."
                    ),
                }

            if user.statut_compte == STATUT_MFA_SETUP_REQUIRED:
                self._audit(
                    action="ACTIVATION_RESEND_MFA_SETUP_REQUIRED",
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="FAIBLE",
                    details={"email": email_clean},
                )
                self.db.commit()
                return {
                    "success": False,
                    "code": "ACCOUNT_MFA_SETUP_REQUIRED",
                    "message": (
                        "Votre mot de passe a déjà été créé. Veuillez terminer "
                        "la configuration Authenticator. Si vous rencontrez un problème, "
                        "réinitialisez votre mot de passe ou contactez l’administrateur."
                    ),
                }

            if user.statut_compte != STATUT_PENDING_ACTIVATION:
                self._audit(
                    action="ACTIVATION_RESEND_NOT_PENDING",
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque="FAIBLE",
                    details={
                        "email": email_clean,
                        "statut_compte": user.statut_compte,
                    },
                )
                self.db.commit()
                return {
                    "success": False,
                    "code": "ACCOUNT_NOT_PENDING_ACTIVATION",
                    "message": (
                        "Ce compte n’est plus en attente d’activation. "
                        "Veuillez vous connecter ou réinitialiser votre mot de passe."
                    ),
                }

            now = utc_now()

            self.db.query(JetonActivation).filter(
                JetonActivation.utilisateur_id == user.id,
                JetonActivation.type_jeton == TOKEN_ACCOUNT_ACTIVATION,
                JetonActivation.utilise_a.is_(None),
            ).delete(synchronize_session=False)

            raw_activation_token = generate_secure_token()

            activation_token = JetonActivation(
                utilisateur_id=user.id,
                jeton_hash=hash_activation_token(raw_activation_token),
                type_jeton=TOKEN_ACCOUNT_ACTIVATION,
                expire_a=now + timedelta(minutes=settings.ACTIVATION_TOKEN_EXPIRE_MINUTES),
                utilise_a=None,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                adresse_ip_creation=adresse_ip,
                user_agent_creation=user_agent,
                details={
                    "resend": True,
                    "expire_minutes": settings.ACTIVATION_TOKEN_EXPIRE_MINUTES,
                },
            )

            self.db.add(activation_token)
            self.db.flush()

            activation_link = (
                f"{settings.FRONTEND_BASE_URL}/activation"
                f"?token={raw_activation_token}"
            )

            self._audit(
                action="ACTIVATION_LINK_RESENT",
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque="MOYEN",
                details={
                    "email": email_clean,
                    "expire_minutes": settings.ACTIVATION_TOKEN_EXPIRE_MINUTES,
                },
            )

            self.mail_service.send_activation_link_email(
                to_email=user.email,
                activation_link=activation_link,
                expire_minutes=settings.ACTIVATION_TOKEN_EXPIRE_MINUTES,
                db=self.db,
                utilisateur_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )

            self.db.commit()
            return generic_response

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur renvoi lien activation: {str(exc)}",
            )

    def complete_activation_password(
        self,
        token: str,
        nouveau_mot_de_passe: str,
        confirmation_mot_de_passe: str,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        try:
            activation = self._get_activation_by_raw_token(token)

            if not activation or not activation.utilisateur:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce lien d’activation est invalide ou a expiré.",
                )

            user = activation.utilisateur
            invalid_reason = self._activation_invalid_reason(activation, user)

            if invalid_reason:
                self._audit(
                    action=AUDIT_ACTIVATION_LINK_INVALID,
                    cible_id=user.id,
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    niveau_risque=RISK_MEDIUM,
                    details={"reason": invalid_reason},
                )
                self.db.commit()

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce lien d’activation est invalide ou a expiré.",
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
            user.statut_compte = STATUT_MFA_SETUP_REQUIRED
            user.nombre_echecs_password = 0
            user.nombre_echecs_totp = 0
            user.blocage_password_jusqu_a = None
            user.blocage_totp_jusqu_a = None
            user.date_dernier_changement_mot_de_passe = now
            user.date_modification = now

            activation.utilise_a = now

            self.db.add(user)
            self.db.add(activation)

            self._audit(
                action=AUDIT_PASSWORD_CREATED,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=RISK_MEDIUM,
            )

            self._audit(
                action=AUDIT_TOTP_SETUP_STARTED,
                cible_id=user.id,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=RISK_MEDIUM,
            )

            setup_token = create_scoped_token(
                data={"sub": str(user.id), "email": user.email},
                purpose="totp_setup",
                expires_delta=timedelta(minutes=10),
            )

            self.db.commit()

            return {
                "success": True,
                "code": "PASSWORD_CREATED_TOTP_REQUIRED",
                "message": "Mot de passe créé avec succès. Veuillez configurer l’authentification TOTP.",
                "email": user.email,
                "next_step": "totp_setup",
                "totp_setup_token": setup_token,
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur activation compte: {str(exc)}",
            )

    def start_totp_setup(self, totp_setup_token: str):
        try:
            payload = decode_scoped_token(totp_setup_token, "totp_setup")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session de configuration TOTP expirée.",
            )

        user = self._get_user_by_id(payload.get("sub"))

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable.",
            )

        if user.statut_compte != STATUT_MFA_SETUP_REQUIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configuration TOTP non autorisée pour ce compte.",
            )

        if self._is_locked(user.blocage_totp_jusqu_a):
            return {
                "success": False,
                "code": "TOTP_SETUP_TEMPORARILY_LOCKED",
                "message": "Configuration TOTP temporairement bloquée.",
                "email": user.email,
                "secret": "",
                "otpauth_url": "",
                "qr_code_base64": "",
            }

        def build_response(raw_secret: str):
            otpauth_url = pyotp.TOTP(raw_secret).provisioning_uri(
                name=user.email,
                issuer_name=settings.TOTP_ISSUER_NAME,
            )

            return {
                "success": True,
                "code": "TOTP_SETUP_READY",
                "message": "Scannez le QR code avec Google Authenticator ou Microsoft Authenticator.",
                "email": user.email,
                "secret": raw_secret,
                "otpauth_url": otpauth_url,
                "qr_code_base64": self._make_qr_base64(otpauth_url),
            }

        def apply_totp_setup(totp_identity: IdentifiantTotp, raw_secret: str):
            now = utc_now()

            totp_identity.secret_chiffre = encrypt_secret(raw_secret)
            totp_identity.est_actif = False
            totp_identity.dernier_pas_utilise = None
            totp_identity.date_activation = None
            totp_identity.date_derniere_utilisation = None
            totp_identity.date_revocation = None
            totp_identity.date_modification = now

            return totp_identity

        secret = pyotp.random_base32()

        try:
            totp_identity = (
                self.db.query(IdentifiantTotp)
                .filter(IdentifiantTotp.utilisateur_id == user.id)
                .first()
            )

            if totp_identity:
                apply_totp_setup(totp_identity, secret)
            else:
                now = utc_now()
                totp_identity = IdentifiantTotp(
                    utilisateur_id=user.id,
                    secret_chiffre=encrypt_secret(secret),
                    est_actif=False,
                    dernier_pas_utilise=None,
                    date_creation=now,
                    date_activation=None,
                    date_derniere_utilisation=None,
                    date_revocation=None,
                    date_modification=now,
                )
                self.db.add(totp_identity)

            self.db.commit()
            return build_response(secret)

        except IntegrityError:
            self.db.rollback()

            # Cas réel observé :
            # deux appels /auth/activation/totp/setup/start arrivent presque en même temps.
            # Les deux SELECT peuvent ne voir aucune ligne, puis les deux tentent un INSERT.
            # Le premier INSERT passe, le deuxième déclenche UniqueViolation.
            # Ici on récupère la ligne créée par l'autre requête et on la met à jour.
            retry_secret = pyotp.random_base32()

            totp_identity = (
                self.db.query(IdentifiantTotp)
                .filter(IdentifiantTotp.utilisateur_id == user.id)
                .first()
            )

            if not totp_identity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Configuration TOTP en cours. Veuillez réessayer.",
                )

            apply_totp_setup(totp_identity, retry_secret)

            self.db.add(totp_identity)
            self.db.commit()

            return build_response(retry_secret)

    def verify_totp_setup(
        self,
        totp_setup_token: str,
        code: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ):
        try:
            payload = decode_scoped_token(totp_setup_token, "totp_setup")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session de configuration TOTP expirée.",
            )

        user = self._get_user_by_id(payload.get("sub"))

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable.",
            )

        if user.statut_compte != STATUT_MFA_SETUP_REQUIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configuration TOTP non autorisée pour ce compte.",
            )

        if self._is_locked(user.blocage_totp_jusqu_a):
            return {
                "success": False,
                "code": "TOTP_SETUP_TEMPORARILY_LOCKED",
                "message": "Configuration TOTP temporairement bloquée.",
                "email": user.email,
                "recovery_codes": [],
                "redirect_to": "/activation/totp",
                "temps_restant": self._format_remaining(user.blocage_totp_jusqu_a),
            }

        totp_identity = (
            self.db.query(IdentifiantTotp)
            .filter(IdentifiantTotp.utilisateur_id == user.id)
            .first()
        )

        if not totp_identity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Veuillez d’abord générer le QR code TOTP.",
            )

        secret = decrypt_secret(totp_identity.secret_chiffre)

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Secret TOTP invalide.",
            )

        cleaned_code = str(code or "").strip().replace(" ", "")
        valid = pyotp.TOTP(secret).verify(cleaned_code, valid_window=1)

        if not valid:
            result = self._handle_totp_setup_failure(
                user=user,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
            )
            self.db.commit()
            return result

        now = utc_now()

        user.statut_compte = STATUT_ACTIVE
        user.nombre_echecs_totp = 0
        user.blocage_totp_jusqu_a = None
        user.date_modification = now

        totp_identity.est_actif = True
        totp_identity.date_activation = now
        totp_identity.date_derniere_utilisation = now
        totp_identity.date_modification = now

        self.db.add(user)
        self.db.add(totp_identity)

        recovery_codes = self._replace_recovery_codes(user.id)

        self._audit(
            action=AUDIT_TOTP_SETUP_SUCCESS,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
        )

        self._audit(
            action=AUDIT_ACCOUNT_ACTIVATED,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
        )

        self.db.commit()

        return {
            "success": True,
            "code": "ACCOUNT_ACTIVATED",
            "message": "Compte activé avec succès. Conservez vos codes de secours.",
            "email": user.email,
            "recovery_codes": recovery_codes,
            "redirect_to": "/login",
            "temps_restant": None,
        }

    def _handle_totp_setup_failure(
        self,
        user: Utilisateur,
        adresse_ip: str | None,
        user_agent: str | None,
    ):
        now = utc_now()
        current = int(user.nombre_echecs_totp or 0)
        new_count = current + 1

        user.nombre_echecs_totp = new_count
        user.date_modification = now

        code = "TOTP_SETUP_INVALID_CODE"
        message = "Code TOTP invalide."
        temps_restant = None
        redirect_to = "/activation/totp"

        if new_count == 4:
            user.blocage_totp_jusqu_a = now + timedelta(seconds=30)
            code = "TOTP_SETUP_DELAY_REQUIRED"
            message = "Plusieurs erreurs TOTP. Veuillez réessayer dans 30 secondes."
            temps_restant = "00:30"

        elif new_count == 5:
            user.blocage_totp_jusqu_a = now + timedelta(seconds=60)
            code = "TOTP_SETUP_DELAY_REQUIRED"
            message = "Plusieurs erreurs TOTP. Veuillez réessayer dans 60 secondes."
            temps_restant = "01:00"

        elif new_count >= 6:
            user.statut_compte = STATUT_PENDING_ACTIVATION
            user.mot_de_passe_hash = None
            user.nombre_echecs_password = 0
            user.nombre_echecs_totp = 0
            user.blocage_password_jusqu_a = None
            user.blocage_totp_jusqu_a = None
            code = "TOTP_SETUP_FAILED_RETURN_ACTIVATION"
            message = "Trop d’erreurs TOTP. Veuillez recommencer l’activation."
            redirect_to = "/activation"

        self.db.add(user)

        self._audit(
            action=AUDIT_TOTP_SETUP_FAILED,
            cible_id=user.id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            niveau_risque="MOYEN",
            details={"attempt": new_count},
        )

        return {
            "success": False,
            "code": code,
            "message": message,
            "email": user.email,
            "recovery_codes": [],
            "redirect_to": redirect_to,
            "temps_restant": temps_restant,
        }

    def _replace_recovery_codes(self, user_id) -> list[str]:
        self.db.query(CodeSecours).filter(
            CodeSecours.utilisateur_id == user_id
        ).delete(synchronize_session=False)

        raw_codes: list[str] = []

        for _ in range(10):
            code = generate_numeric_code(10)
            raw_codes.append(code)

            self.db.add(
                CodeSecours(
                    utilisateur_id=user_id,
                    code_hash=hash_recovery_code(code),
                    est_utilise=False,
                    utilise_a=None,
                )
            )

        self.db.flush()
        return raw_codes

    def _get_activation_by_raw_token(self, token: str):
        return (
            self.db.query(JetonActivation)
            .options(selectinload(JetonActivation.utilisateur))
            .filter(JetonActivation.jeton_hash == hash_activation_token(token))
            .filter(JetonActivation.type_jeton == TOKEN_ACCOUNT_ACTIVATION)
            .first()
        )

    def _activation_invalid_reason(
        self,
        activation: JetonActivation,
        user: Utilisateur,
    ) -> str | None:
        expire_a = ensure_aware_utc(activation.expire_a)

        if activation.utilise_a is not None:
            return "token_already_used"

        if expire_a and expire_a <= utc_now():
            return "token_expired"

        if user.statut_compte != STATUT_PENDING_ACTIVATION:
            return "account_not_pending_activation"

        return None

    def _activation_invalid_response(self, code: str = "ACTIVATION_LINK_INVALID"):
        return {
            "success": False,
            "code": code,
            "message": "Ce lien d’activation est invalide ou a expiré. Veuillez demander un nouveau lien d’activation.",
        }

    def _get_user_by_id(self, user_id):
        return (
            self.db.query(Utilisateur)
            .filter(Utilisateur.id == user_id)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
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

    def _make_qr_base64(self, data: str) -> str:
        img = qrcode.make(data)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

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
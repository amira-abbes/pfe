from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.constants import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    SESSION_REVOKED,
    STATUT_ACTIVE,
    STATUT_BLOQUE_TENTATIVES,
    STATUT_DISABLED,
    STATUT_PENDING_ACTIVATION,
    STATUT_SUPPRIME,
    TOKEN_ACCOUNT_ACTIVATION,
)
from app.core.security import generate_raw_activation_token, hash_activation_token, utc_now
from app.models.departement import Departement
from app.models.jeton_activation import JetonActivation
from app.models.journal_audit import JournalAudit
from app.models.session_utilisateur import SessionUtilisateur
from app.models.utilisateur import Utilisateur
from app.services.mail_service import MailService


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.mail_service = MailService()

    def _is_super_admin(self, user: Utilisateur) -> bool:
        return str(user.role or "").upper() == ROLE_SUPER_ADMIN

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

    def _assert_can_manage_user(self, actor: Utilisateur, target: Utilisateur) -> None:
        if self._is_super_admin(actor):
            if str(target.role or "").upper() == ROLE_SUPER_ADMIN and target.id != actor.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"status": "forbidden", "message": "Accès refusé."},
                )
            return

        if str(actor.role or "").upper() != ROLE_ADMIN or not actor.departement_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "forbidden", "message": "Accès refusé."},
            )

        if target.departement_id != actor.departement_id or str(target.role or "").upper() != ROLE_USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "forbidden", "message": "Accès refusé."},
            )

    def create_user(
        self,
        email: str,
        nom_complet: str,
        departement_nom: str | None,
        admin_user: Utilisateur,
        role: str = ROLE_USER,
    ):
        try:
            email_clean = str(email).strip().lower()
            nom_clean = str(nom_complet).strip()
            role_clean = str(role or ROLE_USER).strip().upper()

            if not nom_clean:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "status": "invalid_input",
                        "message": "Le nom complet est obligatoire.",
                    },
                )

            if role_clean not in {ROLE_USER, ROLE_ADMIN}:
                role_clean = ROLE_USER

            if self._is_super_admin(admin_user):
                departement_clean = str(departement_nom or "").strip()

                if not departement_clean:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "status": "invalid_input",
                            "message": "Le département est obligatoire.",
                        },
                    )

                departement = (
                    self.db.query(Departement)
                    .filter(Departement.nom_departement.ilike(departement_clean))
                    .first()
                )

                if not departement:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "status": "not_found",
                            "message": "Département introuvable.",
                        },
                    )

            else:
                if str(admin_user.role or "").upper() != ROLE_ADMIN:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "status": "forbidden",
                            "message": "Accès refusé.",
                        },
                    )

                if not admin_user.departement_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "status": "forbidden",
                            "message": "Aucun département n’est associé à cet administrateur.",
                        },
                    )

                role_clean = ROLE_USER

                departement = (
                    self.db.query(Departement)
                    .filter(Departement.id == admin_user.departement_id)
                    .first()
                )

                if not departement:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "status": "forbidden",
                            "message": "Le département de cet administrateur est introuvable.",
                        },
                    )

            now = utc_now()

            existing_user = (
                self.db.query(Utilisateur)
                .filter(Utilisateur.email == email_clean)
                .first()
            )

            if existing_user and existing_user.date_suppression is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "status": "user_exists",
                        "message": "Un utilisateur avec cet email existe déjà.",
                    },
                )

            if existing_user and existing_user.date_suppression is not None:
                user = existing_user

                user.nom_complet = nom_clean
                user.departement_id = departement.id
                user.mot_de_passe_hash = None
                user.est_actif = False
                user.role = role_clean
                user.statut_compte = STATUT_PENDING_ACTIVATION
                user.nombre_echecs_password = 0
                user.nombre_echecs_totp = 0
                user.blocage_password_jusqu_a = None
                user.blocage_totp_jusqu_a = None
                user.date_derniere_connexion = None
                user.date_dernier_changement_mot_de_passe = None
                user.date_derniere_alerte_securite = None
                user.date_modification = now
                user.date_desactivation = None
                user.date_suppression = None
                user.cree_par = admin_user.id

                self.db.add(user)
                self.db.flush()

                self.db.query(SessionUtilisateur).filter(
                    SessionUtilisateur.utilisateur_id == user.id
                ).delete(synchronize_session=False)

            else:
                user = Utilisateur(
                    email=email_clean,
                    nom_complet=nom_clean,
                    departement_id=departement.id,
                    mot_de_passe_hash=None,
                    est_actif=False,
                    role=role_clean,
                    statut_compte=STATUT_PENDING_ACTIVATION,
                    nombre_echecs_password=0,
                    nombre_echecs_totp=0,
                    blocage_password_jusqu_a=None,
                    blocage_totp_jusqu_a=None,
                    date_derniere_connexion=None,
                    date_dernier_changement_mot_de_passe=None,
                    date_derniere_alerte_securite=None,
                    date_creation=now,
                    date_modification=now,
                    date_desactivation=None,
                    date_suppression=None,
                    cree_par=admin_user.id,
                )

                self.db.add(user)
                self.db.flush()

            self.db.query(JetonActivation).filter(
                JetonActivation.utilisateur_id == user.id,
                JetonActivation.utilise_a.is_(None),
            ).delete(synchronize_session=False)

            raw_activation_token = generate_raw_activation_token()

            activation_token = JetonActivation(
                utilisateur_id=user.id,
                jeton_hash=hash_activation_token(raw_activation_token),
                type_jeton=TOKEN_ACCOUNT_ACTIVATION,
                expire_a=now
                + timedelta(minutes=settings.ACTIVATION_FIRST_TOKEN_EXPIRE_MINUTES),
                utilise_a=None,
                adresse_ip_creation=None,
                user_agent_creation=None,
                adresse_ip=None,
                user_agent=None,
                details={"first_link": True},
            )

            self.db.add(activation_token)
            self.db.flush()

            activation_link = (
                f"{settings.FRONTEND_BASE_URL}/activation"
                f"?token={raw_activation_token}"
            )

            self.db.add(
                JournalAudit(
                    utilisateur_acteur_id=admin_user.id,
                    cible_utilisateur_id=user.id,
                    action_effectuee="ADMIN_CREATE_USER",
                    niveau_risque="MOYEN",
                    details={
                        "email": email_clean,
                        "departement": departement.nom_departement,
                        "role": role_clean,
                        "reactivation": bool(existing_user),
                        "activation_link_expire_minutes": settings.ACTIVATION_FIRST_TOKEN_EXPIRE_MINUTES,
                    },
                )
            )

            email_sent = self.mail_service.send_activation_link_email(
                to_email=user.email,
                activation_link=activation_link,
                expire_minutes=settings.ACTIVATION_FIRST_TOKEN_EXPIRE_MINUTES,
                db=self.db,
                utilisateur_id=user.id,
            )

            self.db.commit()

            return {
                "utilisateur_id": user.id,
                "email": user.email,
                "nom_complet": user.nom_complet,
                "departement_nom": departement.nom_departement,
                "role": user.role,
                "statut_compte": self._account_status(user),
                "est_actif": user.est_actif,
                "activation_email_sent": email_sent,
                "activation_link_debug": activation_link if settings.MAIL_DEBUG_MODE else None,
                "message": "Utilisateur créé. Un email d’activation a été envoyé.",
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur interne création utilisateur: {str(exc)}",
                },
            )

    def list_users(self, admin_user: Utilisateur):
        try:
            query = (
                self.db.query(Utilisateur)
                .options(selectinload(Utilisateur.departement))
                .filter(Utilisateur.date_suppression.is_(None))
            )

            if not self._is_super_admin(admin_user):
                query = query.filter(Utilisateur.departement_id == admin_user.departement_id)
                query = query.filter(Utilisateur.role == ROLE_USER)

            users = query.order_by(Utilisateur.date_creation.desc()).all()

            return [
                {
                    "id": user.id,
                    "email": user.email,
                    "nom_complet": user.nom_complet,
                    "est_actif": user.est_actif,
                    "role": user.role,
                    "statut_compte": self._account_status(user),
                    "departement_nom": (
                        user.departement.nom_departement
                        if user.departement
                        else None
                    ),
                    "date_creation": user.date_creation,
                    "date_derniere_connexion": user.date_derniere_connexion,
                    "date_desactivation": user.date_desactivation,
                    "date_suppression": user.date_suppression,
                }
                for user in users
            ]

        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur interne lecture utilisateurs: {str(exc)}",
            )

    def get_user_detail_by_email(self, email: str, admin_user: Utilisateur):
        user = (
            self.db.query(Utilisateur)
            .options(selectinload(Utilisateur.departement))
            .filter(Utilisateur.email == email.strip().lower())
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable.",
            )

        self._assert_can_manage_user(admin_user, user)

        return {
            "id": user.id,
            "email": user.email,
            "nom_complet": user.nom_complet,
            "est_actif": user.est_actif,
            "role": user.role,
            "statut_compte": self._account_status(user),
            "departement_nom": (
                user.departement.nom_departement
                if user.departement
                else None
            ),
            "date_creation": user.date_creation,
            "date_modification": user.date_modification,
            "date_derniere_connexion": user.date_derniere_connexion,
            "date_dernier_changement_mot_de_passe": user.date_dernier_changement_mot_de_passe,
            "date_desactivation": user.date_desactivation,
            "date_suppression": user.date_suppression,
            "cree_par": user.cree_par,
        }

    def update_user_status_by_email(
        self,
        email: str,
        est_actif: bool,
        admin_user: Utilisateur,
    ):
        try:
            user = (
                self.db.query(Utilisateur)
                .filter(Utilisateur.email == email.strip().lower())
                .filter(Utilisateur.date_suppression.is_(None))
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Utilisateur introuvable.",
                )

            self._assert_can_manage_user(admin_user, user)

            now = utc_now()

            if est_actif:
                if self._account_status(user) not in {STATUT_DISABLED, STATUT_BLOQUE_TENTATIVES}:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "status": "reactivation_forbidden",
                            "message": "Ce compte ne peut pas être réactivé par cette action.",
                        },
                    )
                user.est_actif = True
                user.statut_compte = STATUT_ACTIVE
                user.date_desactivation = None
                user.nombre_echecs_password = 0
                user.nombre_echecs_totp = 0
                user.blocage_password_jusqu_a = None
                user.blocage_totp_jusqu_a = None
                user.recovery_code_failed_attempts = 0
                user.recovery_code_cooldown_until = None
                user.recovery_code_last_failure_at = None
                user.recovery_code_alert_sent_at = None
                user.recovery_code_warning_sent_at = None
                user.recovery_secure_link_required = False
                user.recovery_secure_link_expires_at = None
                self.mail_service.send_security_alert_email(
                    to_email=user.email,
                    subject="Compte administrateur réactivé" if str(user.role or "").upper() == ROLE_ADMIN else "Compte réactivé",
                    message=(
                        "Votre compte administrateur a été réactivé par le super administrateur.\n\n"
                        "Vous pouvez maintenant vous connecter à la plateforme."
                        if str(user.role or "").upper() == ROLE_ADMIN
                        else "Votre compte a été réactivé par votre administrateur.\n\nVous pouvez maintenant vous connecter à la plateforme."
                    ),
                    db=self.db,
                    utilisateur_id=user.id,
                    details={"type": "ACCOUNT_REACTIVATED", "actor": admin_user.email},
                )
            else:
                if user.id == admin_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "status": "self_deactivation_forbidden",
                            "message": "Vous ne pouvez pas désactiver votre propre compte.",
                        },
                    )
                if self._account_status(user) != STATUT_ACTIVE or not user.est_actif:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "status": "deactivation_forbidden",
                            "message": "Seul un compte actif peut être désactivé.",
                        },
                    )
                user.est_actif = False
                user.statut_compte = STATUT_DISABLED
                user.date_desactivation = now
                self.db.query(SessionUtilisateur).filter(
                    SessionUtilisateur.utilisateur_id == user.id,
                    SessionUtilisateur.revoque_a.is_(None),
                ).update(
                    {
                        "revoque_a": now,
                        "raison_revocation": "Compte désactivé par administrateur",
                        "statut_session": SESSION_REVOKED,
                    },
                    synchronize_session=False,
                )

            user.date_modification = now
            self.db.add(user)

            self.db.add(
                JournalAudit(
                    utilisateur_acteur_id=admin_user.id,
                    cible_utilisateur_id=user.id,
                    action_effectuee="ADMIN_UPDATE_USER_STATUS",
                    niveau_risque="MOYEN",
                    details={
                        "email": user.email,
                        "est_actif": est_actif,
                    },
                )
            )

            self.db.commit()

            return {
                "success": True,
                "message": "Compte réactivé avec succès." if est_actif else "Compte désactivé avec succès.",
                "email": user.email,
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur interne mise à jour statut: {str(exc)}",
            )

    def update_user_profile_by_email(
        self,
        email: str,
        departement_nom: str,
        admin_user: Utilisateur,
    ):
        try:
            if not self._is_super_admin(admin_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "status": "forbidden",
                        "message": "Accès refusé.",
                    },
                )

            user = (
                self.db.query(Utilisateur)
                .options(selectinload(Utilisateur.departement))
                .filter(Utilisateur.email == email.strip().lower())
                .filter(Utilisateur.date_suppression.is_(None))
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Utilisateur introuvable.",
                )

            self._assert_can_manage_user(admin_user, user)

            departement_clean = str(departement_nom or "").strip()

            departement = (
                self.db.query(Departement)
                .filter(Departement.nom_departement.ilike(departement_clean))
                .first()
            )

            if not departement:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Département introuvable.",
                )

            old_departement = (
                user.departement.nom_departement if user.departement else None
            )

            user.departement_id = departement.id
            user.date_modification = utc_now()

            self.db.add(user)

            self.db.add(
                JournalAudit(
                    utilisateur_acteur_id=admin_user.id,
                    cible_utilisateur_id=user.id,
                    action_effectuee="ADMIN_UPDATE_USER_PROFILE",
                    niveau_risque="MOYEN",
                    details={
                        "email": user.email,
                        "old_departement": old_departement,
                        "new_departement": departement.nom_departement,
                    },
                )
            )

            self.db.commit()

            return {
                "success": True,
                "message": "Département utilisateur mis à jour avec succès.",
                "email": user.email,
                "role": user.role,
                "departement_nom": departement.nom_departement,
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur interne mise à jour profil: {str(exc)}",
            )

    def delete_user_by_email(self, email: str, admin_user: Utilisateur):
        try:
            user = (
                self.db.query(Utilisateur)
                .filter(Utilisateur.email == email.strip().lower())
                .filter(Utilisateur.date_suppression.is_(None))
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Utilisateur introuvable.",
                )

            self._assert_can_manage_user(admin_user, user)

            now = utc_now()
            user_email = user.email

            user.est_actif = False
            user.statut_compte = STATUT_SUPPRIME
            user.date_suppression = now
            user.date_desactivation = now
            user.date_modification = now

            self.db.query(SessionUtilisateur).filter(
                SessionUtilisateur.utilisateur_id == user.id,
                SessionUtilisateur.revoque_a.is_(None),
            ).update(
                {
                    "revoque_a": now,
                    "raison_revocation": "Utilisateur supprimé par administrateur",
                    "statut_session": SESSION_REVOKED,
                },
                synchronize_session=False,
            )

            self.db.add(user)

            self.db.add(
                JournalAudit(
                    utilisateur_acteur_id=admin_user.id,
                    cible_utilisateur_id=user.id,
                    action_effectuee="ADMIN_DELETE_USER",
                    niveau_risque="ELEVE",
                    details={"email": user_email},
                )
            )

            self.db.commit()

            return {
                "success": True,
                "message": "Utilisateur supprimé avec succès.",
                "email": user_email,
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur interne suppression utilisateur: {str(exc)}",
            )

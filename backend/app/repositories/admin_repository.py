from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.security import hash_activation_token
from app.models.departement import Departement
from app.models.jeton_activation import JetonActivation
from app.models.utilisateur import Utilisateur


class AdminRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> Utilisateur | None:
        return (
            self.db.query(Utilisateur)
            .options(selectinload(Utilisateur.departement))
            .filter(Utilisateur.email == email)
            .filter(Utilisateur.date_suppression.is_(None))
            .first()
        )

    def get_departement_by_nom(self, nom_departement: str) -> Departement | None:
        return (
            self.db.query(Departement)
            .filter(Departement.nom_departement == nom_departement)
            .first()
        )

    def list_users(self) -> list[Utilisateur]:
        return (
            self.db.query(Utilisateur)
            .options(selectinload(Utilisateur.departement))
            .filter(Utilisateur.date_suppression.is_(None))
            .order_by(Utilisateur.date_creation.desc())
            .all()
        )

    def create_user(
        self,
        email: str,
        nom_complet: str,
        departement_id: UUID,
        cree_par: UUID | None,
    ) -> Utilisateur:
        now = datetime.now(timezone.utc)

        user = Utilisateur(
            email=email,
            nom_complet=nom_complet,
            departement_id=departement_id,
            mot_de_passe_hash=None,
            est_actif=True,
            role="USER",
            statut_compte="PENDING_ACTIVATION",
            nombre_echecs_password=0,
            nombre_echecs_totp=0,
            blocage_password_jusqu_a=None,
            blocage_totp_jusqu_a=None,
            date_creation=now,
            date_modification=now,
            date_desactivation=None,
            date_suppression=None,
            cree_par=cree_par,
        )

        self.db.add(user)
        self.db.flush()
        return user

    def create_activation_token(
        self,
        utilisateur_id: UUID,
        raw_token: str,
    ) -> JetonActivation:
        token = JetonActivation(
            utilisateur_id=utilisateur_id,
            jeton_hash=hash_activation_token(raw_token),
            expire_a=datetime.now(timezone.utc)
            + timedelta(minutes=settings.ACTIVATION_TOKEN_EXPIRE_MINUTES),
            utilise_a=None,
        )

        self.db.add(token)
        self.db.flush()
        return token

    def update_user_status(self, user: Utilisateur, est_actif: bool) -> Utilisateur:
        now = datetime.now(timezone.utc)

        user.est_actif = est_actif
        user.date_modification = now
        user.date_desactivation = None if est_actif else now

        self.db.add(user)
        self.db.flush()
        return user

    def soft_delete_user(self, user: Utilisateur) -> None:
        now = datetime.now(timezone.utc)

        user.est_actif = False
        user.date_suppression = now
        user.date_modification = now

        self.db.add(user)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

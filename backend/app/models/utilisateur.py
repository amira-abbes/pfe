from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import Text

from app.core.constants import ROLE_USER, STATUT_PENDING_ACTIVATION
from app.db.base import Base


class Utilisateur(Base):
    __tablename__ = "utilisateurs"
    __table_args__ = (
        Index(
            "ux_utilisateurs_active_admin_per_departement",
            "departement_id",
            unique=True,
            postgresql_where=text(
                "UPPER(role) = 'ADMIN' AND est_actif IS TRUE AND date_suppression IS NULL"
            ),
        ),
        {"schema": "app"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    email = Column(String(255), nullable=False, unique=True)
    nom_complet = Column(String(150), nullable=False)

    mot_de_passe_hash = Column(Text, nullable=True)

    est_actif = Column(Boolean, nullable=False, server_default=text("true"))

    role = Column(String(30), nullable=False, server_default=text(f"'{ROLE_USER}'"))
    statut_compte = Column(
        String(50),
        nullable=False,
        server_default=text(f"'{STATUT_PENDING_ACTIVATION}'"),
    )

    departement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.departements.id", ondelete="SET NULL"),
        nullable=True,
    )

    cree_par = Column(UUID(as_uuid=True), nullable=True)

    nombre_echecs_password = Column(Integer, nullable=False, server_default=text("0"))
    nombre_echecs_totp = Column(Integer, nullable=False, server_default=text("0"))

    blocage_password_jusqu_a = Column(DateTime(timezone=True), nullable=True)
    blocage_totp_jusqu_a = Column(DateTime(timezone=True), nullable=True)

    password_lockout_resolved_at = Column(DateTime(timezone=True), nullable=True)
    password_lockout_mail_sent_at = Column(DateTime(timezone=True), nullable=True)
    password_lockout_mail_expires_at = Column(DateTime(timezone=True), nullable=True)
    password_lockout_requires_mail_action = Column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    recovery_code_failed_attempts = Column(Integer, nullable=False, server_default=text("0"))
    recovery_code_last_failure_at = Column(DateTime(timezone=True), nullable=True)
    recovery_code_cooldown_until = Column(DateTime(timezone=True), nullable=True)
    recovery_code_warning_sent_at = Column(DateTime(timezone=True), nullable=True)
    recovery_code_alert_sent_at = Column(DateTime(timezone=True), nullable=True)
    recovery_secure_link_required = Column(Boolean, nullable=False, server_default=text("false"))
    recovery_secure_link_expires_at = Column(DateTime(timezone=True), nullable=True)

    date_derniere_connexion = Column(DateTime(timezone=True), nullable=True)
    date_dernier_changement_mot_de_passe = Column(DateTime(timezone=True), nullable=True)
    date_derniere_alerte_securite = Column(DateTime(timezone=True), nullable=True)

    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    date_modification = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    date_desactivation = Column(DateTime(timezone=True), nullable=True)
    date_suppression = Column(DateTime(timezone=True), nullable=True)

    departement = relationship("Departement", back_populates="utilisateurs")

    sessions = relationship(
        "SessionUtilisateur",
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    identifiant_totp = relationship(
        "IdentifiantTotp",
        back_populates="utilisateur",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    codes_secours = relationship(
        "CodeSecours",
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    jetons_reinitialisation = relationship(
        "JetonReinitialisationMotDePasse",
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    tentatives_connexion = relationship(
        "TentativeConnexion",
        back_populates="utilisateur",
        passive_deletes=True,
    )

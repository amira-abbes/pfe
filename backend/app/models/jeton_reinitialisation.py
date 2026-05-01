from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.constants import TOKEN_PASSWORD_RESET
from app.db.base import Base


class JetonReinitialisationMotDePasse(Base):
    __tablename__ = "jetons_reinitialisation_mot_de_passe"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
    )

    jeton_hash = Column(Text, nullable=False, unique=True)
    type_jeton = Column(
        String(80),
        nullable=False,
        server_default=text(f"'{TOKEN_PASSWORD_RESET}'"),
    )
    type_token = Column(String(80), nullable=True)
    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    expire_a = Column(DateTime(timezone=True), nullable=False)
    utilise_a = Column(DateTime(timezone=True), nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    adresse_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    mfa_echecs_totp = Column(Integer, nullable=False, server_default=text("0"))
    mfa_dernier_echec_a = Column(DateTime(timezone=True), nullable=True)
    mfa_cooldown_jusqu_a = Column(DateTime(timezone=True), nullable=True)
    mfa_totp_bloque = Column(Boolean, nullable=False, server_default=text("false"))
    mfa_echecs_recovery = Column(Integer, nullable=False, server_default=text("0"))
    mfa_recovery_bloque_jusqu_a = Column(DateTime(timezone=True), nullable=True)

    utilisateur = relationship("Utilisateur", back_populates="jetons_reinitialisation")

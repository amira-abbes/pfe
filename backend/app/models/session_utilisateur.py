from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import relationship

from app.core.constants import SESSION_ACTIVE
from app.db.base import Base


class SessionUtilisateur(Base):
    __tablename__ = "sessions_utilisateur"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
    )

    jeton_session_hash = Column(Text, nullable=False, unique=True)

    role = Column(String(30), nullable=False)
    statut_session = Column(
        String(50),
        nullable=False,
        server_default=text(f"'{SESSION_ACTIVE}'"),
    )
    methode_mfa = Column(String(50), nullable=True)

    adresse_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    derniere_activite_a = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expire_a = Column(DateTime(timezone=True), nullable=False)

    revoque_a = Column(DateTime(timezone=True), nullable=True)
    raison_revocation = Column(String(255), nullable=True)

    utilisateur = relationship("Utilisateur", back_populates="sessions")
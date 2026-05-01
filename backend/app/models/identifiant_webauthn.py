from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class IdentifiantWebAuthn(Base):
    __tablename__ = "identifiants_webauthn"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
    )

    credential_id = Column(Text, nullable=False, unique=True)
    cle_publique = Column(Text, nullable=False)
    compteur_signature = Column(BigInteger, nullable=False, server_default=text("0"))

    nom_appareil = Column(String(150), nullable=False)
    est_actif = Column(Boolean, nullable=False, server_default=text("true"))

    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    date_derniere_utilisation = Column(DateTime(timezone=True), nullable=True)
    date_revocation = Column(DateTime(timezone=True), nullable=True)

    utilisateur = relationship("Utilisateur", back_populates="identifiants_webauthn")
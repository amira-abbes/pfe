from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class IdentifiantTotp(Base):
    __tablename__ = "identifiants_totp"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    secret_chiffre = Column(Text, nullable=False)
    est_actif = Column(Boolean, nullable=False, server_default=text("false"))

    dernier_pas_utilise = Column(Text, nullable=True)

    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    date_activation = Column(DateTime(timezone=True), nullable=True)
    date_derniere_utilisation = Column(DateTime(timezone=True), nullable=True)
    date_revocation = Column(DateTime(timezone=True), nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    utilisateur = relationship("Utilisateur", back_populates="identifiant_totp")

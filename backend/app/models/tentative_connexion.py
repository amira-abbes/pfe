from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class TentativeConnexion(Base):
    __tablename__ = "tentatives_connexion"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="SET NULL"),
        nullable=True,
    )

    email_saisi = Column(String(255), nullable=False)
    type_tentative = Column(String(80), nullable=False)

    succes = Column(Boolean, nullable=False)
    raison_echec = Column(String(150), nullable=True)
    niveau_risque = Column(String(30), nullable=False, server_default=text("'FAIBLE'"))

    adresse_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    date_tentative = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    utilisateur = relationship("Utilisateur", back_populates="tentatives_connexion")
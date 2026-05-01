from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from app.db.base import Base


class NotificationSecurite(Base):
    __tablename__ = "notifications_securite"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
    )

    type_notification = Column(String(80), nullable=False)
    email_destinataire = Column(String(255), nullable=False)
    sujet = Column(String(255), nullable=False)

    statut = Column(String(50), nullable=False, server_default=text("'EN_ATTENTE'"))
    erreur_envoi = Column(Text, nullable=True)

    adresse_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    date_envoi = Column(DateTime(timezone=True), nullable=True)
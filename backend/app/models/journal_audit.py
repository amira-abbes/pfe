from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from app.db.base import Base


class JournalAudit(Base):
    __tablename__ = "journal_audit"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_acteur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="SET NULL"),
        nullable=True,
    )

    cible_utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="SET NULL"),
        nullable=True,
    )

    action_effectuee = Column(String(150), nullable=False)
    niveau_risque = Column(String(30), nullable=False, server_default=text("'FAIBLE'"))

    adresse_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    date_action = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
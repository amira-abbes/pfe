from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.constants import TOKEN_ACCOUNT_ACTIVATION
from app.db.base import Base


class JetonActivation(Base):
    __tablename__ = "jetons_activation"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
    )

    jeton_hash = Column(Text, nullable=False, unique=True)
    type_jeton = Column(
        String(50),
        nullable=False,
        server_default=text(f"'{TOKEN_ACCOUNT_ACTIVATION}'"),
    )

    expire_a = Column(DateTime(timezone=True), nullable=False)
    utilise_a = Column(DateTime(timezone=True), nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    adresse_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    adresse_ip_creation = Column(INET, nullable=True)
    user_agent_creation = Column(Text, nullable=True)

    utilisateur = relationship("Utilisateur")
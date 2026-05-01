from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class CodeSecours(Base):
    __tablename__ = "codes_secours"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    utilisateur_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.utilisateurs.id", ondelete="CASCADE"),
        nullable=False,
    )

    code_hash = Column(Text, nullable=False)

    utilise = Column(Boolean, nullable=False, server_default=text("false"))
    est_utilise = Column(Boolean, nullable=False, server_default=text("false"))

    utilise_a = Column(DateTime(timezone=True), nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    date_expiration = Column(DateTime(timezone=True), nullable=True)

    utilisateur = relationship("Utilisateur", back_populates="codes_secours")
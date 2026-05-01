from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Departement(Base):
    __tablename__ = "departements"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nom_departement = Column(String(100), nullable=False, unique=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    utilisateurs = relationship("Utilisateur", back_populates="departement")

    departement_droits = relationship(
        "DepartementDroit",
        back_populates="departement",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
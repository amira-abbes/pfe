from sqlalchemy import Column, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class DroitAcces(Base):
    __tablename__ = "droits_acces"
    __table_args__ = {"schema": "app"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nom_droit = Column(String(150), nullable=False, unique=True)

    departement_droits = relationship(
        "DepartementDroit",
        back_populates="droit_acces",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
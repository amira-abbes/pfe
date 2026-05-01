from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class DepartementDroit(Base):
    __tablename__ = "departement_droits"
    __table_args__ = {"schema": "app"}

    departement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.departements.id", ondelete="CASCADE"),
        primary_key=True,
    )

    droit_acces_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app.droits_acces.id", ondelete="CASCADE"),
        primary_key=True,
    )

    departement = relationship("Departement", back_populates="departement_droits")
    droit_acces = relationship("DroitAcces", back_populates="departement_droits")
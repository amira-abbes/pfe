from sqlalchemy.orm import Session, selectinload

from app.models.departement import Departement
from app.models.departement_droit import DepartementDroit
from app.models.droit_acces import DroitAcces


class AdminDepartementsRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_departements(self) -> list[Departement]:
        return (
            self.db.query(Departement)
            .order_by(Departement.nom_departement.asc())
            .all()
        )

    def get_departement_by_nom(self, nom_departement: str) -> Departement | None:
        return (
            self.db.query(Departement)
            .options(
                selectinload(Departement.departement_droits)
                .selectinload(DepartementDroit.droit_acces)
            )
            .filter(Departement.nom_departement == nom_departement)
            .first()
        )

    def create_departement(self, nom_departement: str) -> Departement:
        departement = Departement(nom_departement=nom_departement.strip())
        self.db.add(departement)
        self.db.flush()
        return departement

    def list_droits(self) -> list[DroitAcces]:
        return (
            self.db.query(DroitAcces)
            .order_by(DroitAcces.nom_droit.asc())
            .all()
        )

    def get_droit_by_nom(self, nom_droit: str) -> DroitAcces | None:
        return (
            self.db.query(DroitAcces)
            .filter(DroitAcces.nom_droit == nom_droit)
            .first()
        )

    def get_droits_by_noms(self, droit_noms: list[str]) -> list[DroitAcces]:
        return (
            self.db.query(DroitAcces)
            .filter(DroitAcces.nom_droit.in_(droit_noms))
            .all()
        )

    def create_droit(self, nom_droit: str) -> DroitAcces:
        droit = DroitAcces(nom_droit=nom_droit.strip())
        self.db.add(droit)
        self.db.flush()
        return droit

    def replace_departement_rights(self, departement: Departement, droit_ids: list):
        self.db.query(DepartementDroit).filter(
            DepartementDroit.departement_id == departement.id
        ).delete()

        for droit_id in droit_ids:
            self.db.add(
                DepartementDroit(
                    departement_id=departement.id,
                    droit_acces_id=droit_id,
                )
            )

        self.db.flush()

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.departement import Departement
from app.models.departement_droit import DepartementDroit
from app.models.droit_acces import DroitAcces
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur


class AdminDepartementsService:
    def __init__(self, db: Session):
        self.db = db

    def _clean_name(self, value: str) -> str:
        return str(value or "").strip()

    def _normalize_name(self, value: str) -> str:
        return self._clean_name(value).lower()

    def list_departements(self):
        departements = (
            self.db.query(Departement)
            .order_by(func.lower(Departement.nom_departement).asc())
            .all()
        )

        return [
            {
                "id": item.id,
                "nom_departement": item.nom_departement,
            }
            for item in departements
        ]

    def create_departement(self, nom_departement: str, admin_user: Utilisateur):
        nom = self._clean_name(nom_departement)

        if not nom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "status": "invalid_input",
                    "message": "Le nom du département est obligatoire.",
                },
            )

        existing = (
            self.db.query(Departement)
            .filter(func.lower(Departement.nom_departement) == nom.lower())
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "status": "department_exists",
                    "message": "Ce département existe déjà.",
                },
            )

        try:
            departement = Departement(nom_departement=nom)
            self.db.add(departement)

            self._audit(
                admin_user=admin_user,
                action="ADMIN_DEPARTMENT_CREATED",
                details={"nom_departement": nom},
            )

            self.db.commit()
            self.db.refresh(departement)

            return {
                "id": departement.id,
                "nom_departement": departement.nom_departement,
            }

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur création département: {str(exc)}",
                },
            )

    def delete_departement_by_nom(
        self,
        nom_departement: str,
        admin_user: Utilisateur,
    ):
        departement = self._get_departement_by_nom(nom_departement)

        users_count = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.departement_id == departement.id)
            .filter(Utilisateur.date_suppression.is_(None))
            .count()
        )

        if users_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "status": "department_has_users",
                    "message": (
                        "Impossible de supprimer ce département car il contient encore "
                        "des utilisateurs. Veuillez réaffecter ou supprimer ces "
                        "utilisateurs avant de continuer."
                    ),
                },
            )

        try:
            nom = departement.nom_departement

            self._audit(
                admin_user=admin_user,
                action="ADMIN_DEPARTMENT_DELETED",
                details={"nom_departement": nom},
                niveau_risque="ELEVE",
            )

            self.db.query(DepartementDroit).filter(
                DepartementDroit.departement_id == departement.id
            ).delete(synchronize_session=False)

            self.db.delete(departement)
            self.db.commit()

            return {
                "success": True,
                "status": "success",
                "message": "Département supprimé avec succès.",
                "nom_departement": nom,
            }

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur suppression département: {str(exc)}",
                },
            )

    def list_droits(self):
        droits = (
            self.db.query(DroitAcces)
            .order_by(func.lower(DroitAcces.nom_droit).asc())
            .all()
        )

        return [
            {
                "id": item.id,
                "nom_droit": item.nom_droit,
            }
            for item in droits
        ]

    def create_droit(self, nom_droit: str, admin_user: Utilisateur):
        nom = self._clean_name(nom_droit)

        if not nom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "status": "invalid_input",
                    "message": "Le nom du droit est obligatoire.",
                },
            )

        existing = (
            self.db.query(DroitAcces)
            .filter(func.lower(DroitAcces.nom_droit) == nom.lower())
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "status": "right_exists",
                    "message": "Ce droit existe déjà.",
                },
            )

        try:
            droit = DroitAcces(nom_droit=nom)
            self.db.add(droit)

            self._audit(
                admin_user=admin_user,
                action="ADMIN_PERMISSION_CREATED",
                details={"nom_droit": nom},
            )

            self.db.commit()
            self.db.refresh(droit)

            return {
                "id": droit.id,
                "nom_droit": droit.nom_droit,
            }

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur création droit: {str(exc)}",
                },
            )

    def get_department_rights_by_nom(self, nom_departement: str):
        departement = (
            self.db.query(Departement)
            .options(
                selectinload(Departement.departement_droits)
                .selectinload(DepartementDroit.droit_acces)
            )
            .filter(
                func.lower(Departement.nom_departement)
                == self._normalize_name(nom_departement)
            )
            .first()
        )

        if not departement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "not_found",
                    "message": "Département introuvable.",
                },
            )

        droits = [
            relation.droit_acces
            for relation in departement.departement_droits
            if relation.droit_acces
        ]

        droits.sort(key=lambda item: item.nom_droit.lower())

        return {
            "departement_nom": departement.nom_departement,
            "droits": [
                {
                    "id": droit.id,
                    "nom_droit": droit.nom_droit,
                }
                for droit in droits
            ],
        }

    def assign_rights_to_departement_by_nom(
        self,
        nom_departement: str,
        droit_noms: list[str],
        admin_user: Utilisateur,
    ):
        departement = self._get_departement_by_nom(nom_departement)

        droit_noms_clean = sorted(
            {self._clean_name(item) for item in droit_noms if self._clean_name(item)}
        )

        droits = []
        if droit_noms_clean:
            droits = (
                self.db.query(DroitAcces)
                .filter(DroitAcces.nom_droit.in_(droit_noms_clean))
                .all()
            )

        if len(droits) != len(droit_noms_clean):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "not_found",
                    "message": "Un ou plusieurs droits sont introuvables.",
                },
            )

        try:
            previous_droits = self._current_droit_names(departement)
            next_droits = {droit.nom_droit for droit in droits}

            self.db.query(DepartementDroit).filter(
                DepartementDroit.departement_id == departement.id
            ).delete(synchronize_session=False)

            for droit in droits:
                self.db.add(
                    DepartementDroit(
                        departement_id=departement.id,
                        droit_acces_id=droit.id,
                    )
                )

            self._audit_permission_diff(
                admin_user=admin_user,
                departement=departement,
                previous_droits=previous_droits,
                next_droits=next_droits,
            )

            self.db.commit()

            return self.get_department_rights_by_nom(departement.nom_departement)

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur attribution droits département: {str(exc)}",
                },
            )

    def grant_right_to_departement_by_nom(
        self,
        nom_departement: str,
        nom_droit: str,
        admin_user: Utilisateur,
    ):
        departement = self._get_departement_by_nom(nom_departement)
        droit = self._get_droit_by_nom(nom_droit)

        try:
            existing = (
                self.db.query(DepartementDroit)
                .filter(DepartementDroit.departement_id == departement.id)
                .filter(DepartementDroit.droit_acces_id == droit.id)
                .first()
            )

            if not existing:
                self.db.add(
                    DepartementDroit(
                        departement_id=departement.id,
                        droit_acces_id=droit.id,
                    )
                )

                self._audit(
                    admin_user=admin_user,
                    action="ADMIN_DEPARTMENT_PERMISSION_GRANTED",
                    details={
                        "departement": departement.nom_departement,
                        "nom_droit": droit.nom_droit,
                    },
                )

                self.db.commit()

            return self.get_department_rights_by_nom(departement.nom_departement)

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur ajout droit département: {str(exc)}",
                },
            )

    def revoke_right_from_departement_by_nom(
        self,
        nom_departement: str,
        nom_droit: str,
        admin_user: Utilisateur,
    ):
        departement = self._get_departement_by_nom(nom_departement)
        droit = self._get_droit_by_nom(nom_droit)

        try:
            deleted = (
                self.db.query(DepartementDroit)
                .filter(DepartementDroit.departement_id == departement.id)
                .filter(DepartementDroit.droit_acces_id == droit.id)
                .delete(synchronize_session=False)
            )

            if deleted:
                self._audit(
                    admin_user=admin_user,
                    action="ADMIN_DEPARTMENT_PERMISSION_REVOKED",
                    details={
                        "departement": departement.nom_departement,
                        "nom_droit": droit.nom_droit,
                    },
                )

            self.db.commit()

            return self.get_department_rights_by_nom(departement.nom_departement)

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "internal_error",
                    "message": f"Erreur retrait droit département: {str(exc)}",
                },
            )

    def _get_departement_by_nom(self, nom_departement: str) -> Departement:
        nom = self._normalize_name(nom_departement)

        departement = (
            self.db.query(Departement)
            .filter(func.lower(Departement.nom_departement) == nom)
            .first()
        )

        if not departement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "not_found",
                    "message": "Département introuvable.",
                },
            )

        return departement

    def _get_droit_by_nom(self, nom_droit: str) -> DroitAcces:
        nom = self._clean_name(nom_droit)

        droit = (
            self.db.query(DroitAcces)
            .filter(DroitAcces.nom_droit == nom)
            .first()
        )

        if not droit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "not_found",
                    "message": "Droit introuvable.",
                },
            )

        return droit

    def _current_droit_names(self, departement: Departement) -> set[str]:
        relations = (
            self.db.query(DepartementDroit)
            .options(selectinload(DepartementDroit.droit_acces))
            .filter(DepartementDroit.departement_id == departement.id)
            .all()
        )

        return {
            relation.droit_acces.nom_droit
            for relation in relations
            if relation.droit_acces
        }

    def _audit_permission_diff(
        self,
        admin_user: Utilisateur,
        departement: Departement,
        previous_droits: set[str],
        next_droits: set[str],
    ) -> None:
        for droit_nom in sorted(next_droits - previous_droits):
            self._audit(
                admin_user=admin_user,
                action="ADMIN_DEPARTMENT_PERMISSION_GRANTED",
                details={
                    "departement": departement.nom_departement,
                    "nom_droit": droit_nom,
                },
            )

        for droit_nom in sorted(previous_droits - next_droits):
            self._audit(
                admin_user=admin_user,
                action="ADMIN_DEPARTMENT_PERMISSION_REVOKED",
                details={
                    "departement": departement.nom_departement,
                    "nom_droit": droit_nom,
                },
            )

    def _audit(
        self,
        admin_user: Utilisateur,
        action: str,
        details: dict | None = None,
        niveau_risque: str = "MOYEN",
    ) -> None:
        self.db.add(
            JournalAudit(
                utilisateur_acteur_id=admin_user.id,
                action_effectuee=action,
                niveau_risque=niveau_risque,
                details=details or {},
            )
        )
        self.db.flush()
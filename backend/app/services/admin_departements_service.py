from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.constants import ROLE_ADMIN
from app.models.departement import Departement
from app.models.departement_droit import DepartementDroit
from app.models.droit_acces import DroitAcces
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur
from app.core.access_control import (
    BUSINESS_PERMISSION_LABELS,
    BUSINESS_PERMISSION_LANCER_TRAITEMENT_ELT,
    LEGACY_BUSINESS_PERMISSION_VOIR_RESULTAT_ELT,
    valid_business_permissions,
)


class AdminDepartementsService:
    def __init__(self, db: Session):
        self.db = db

    def _clean_name(self, value: str) -> str:
        return str(value or "").strip()

    def _normalize_name(self, value: str) -> str:
        return self._clean_name(value).lower()

    def _business_permission_order(self, nom_droit: str) -> int:
        try:
            return list(BUSINESS_PERMISSION_LABELS).index(nom_droit)
        except ValueError:
            return len(BUSINESS_PERMISSION_LABELS)

    def _serialize_droit(self, droit: DroitAcces) -> dict:
        return {
            "id": droit.id,
            "nom_droit": droit.nom_droit,
            "label": BUSINESS_PERMISSION_LABELS.get(droit.nom_droit, droit.nom_droit),
        }

    def _ensure_business_droits(self) -> dict[str, DroitAcces]:
        valid_names = list(BUSINESS_PERMISSION_LABELS)
        droits = (
            self.db.query(DroitAcces)
            .filter(
                DroitAcces.nom_droit.in_(
                    [*valid_names, LEGACY_BUSINESS_PERMISSION_VOIR_RESULTAT_ELT]
                )
            )
            .all()
        )
        by_name = {droit.nom_droit: droit for droit in droits}

        missing_names = [name for name in valid_names if name not in by_name]
        if missing_names:
            for name in missing_names:
                droit = DroitAcces(nom_droit=name)
                self.db.add(droit)
                by_name[name] = droit
            self.db.commit()
            for droit in by_name.values():
                self.db.refresh(droit)

        self._merge_legacy_elt_permission(by_name)
        by_name.pop(LEGACY_BUSINESS_PERMISSION_VOIR_RESULTAT_ELT, None)

        return by_name

    def _merge_legacy_elt_permission(self, droits_by_name: dict[str, DroitAcces]) -> None:
        legacy = droits_by_name.get(LEGACY_BUSINESS_PERMISSION_VOIR_RESULTAT_ELT)
        target = droits_by_name.get(BUSINESS_PERMISSION_LANCER_TRAITEMENT_ELT)
        if not legacy or not target:
            return

        changed = False
        legacy_relations = (
            self.db.query(DepartementDroit)
            .filter(DepartementDroit.droit_acces_id == legacy.id)
            .all()
        )
        for relation in legacy_relations:
            existing = (
                self.db.query(DepartementDroit)
                .filter(DepartementDroit.departement_id == relation.departement_id)
                .filter(DepartementDroit.droit_acces_id == target.id)
                .first()
            )
            if not existing:
                self.db.add(
                    DepartementDroit(
                        departement_id=relation.departement_id,
                        droit_acces_id=target.id,
                    )
                )
            self.db.delete(relation)
            changed = True

        if changed:
            self.db.flush()

        self.db.delete(legacy)
        self.db.commit()

    def _validate_business_droit_name(self, nom_droit: str) -> str:
        nom = self._clean_name(nom_droit)
        if nom not in valid_business_permissions():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "status": "invalid_permission",
                    "message": "Permission métier inconnue ou obsolète.",
                },
            )
        return nom

    def _validate_permission_allowed_for_department(
        self,
        departement: Departement,
        nom_droit: str,
    ) -> None:
        allowed = valid_business_permissions()
        if nom_droit not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "status": "permission_forbidden_for_department",
                    "message": "Cette permission n'est pas autorisée pour ce département.",
                },
            )

    def _cleanup_invalid_department_rights(self, departement: Departement) -> bool:
        # Si le département n'est pas reconnu par le matching métier,
        # allowed sera un set vide, ce qui effacerait toutes les permissions.
        # Dans ce cas, on ne touche pas aux permissions existantes.
        valid = valid_business_permissions()
        relations = (
            self.db.query(DepartementDroit)
            .options(selectinload(DepartementDroit.droit_acces))
            .filter(DepartementDroit.departement_id == departement.id)
            .all()
        )

        changed = False
        for relation in relations:
            name = relation.droit_acces.nom_droit if relation.droit_acces else None
            if name not in valid:
                self.db.delete(relation)
                changed = True

        if changed:
            self.db.commit()

        return changed

    def list_departements(self):
        departements = (
            self.db.query(Departement)
            .order_by(func.lower(Departement.nom_departement).asc())
            .all()
        )
        active_admins = (
            self.db.query(
                Utilisateur.departement_id,
                func.min(Utilisateur.email).label("email"),
                func.count(Utilisateur.id).label("count"),
            )
            .filter(func.upper(Utilisateur.role) == ROLE_ADMIN)
            .filter(Utilisateur.est_actif.is_(True))
            .filter(Utilisateur.date_suppression.is_(None))
            .group_by(Utilisateur.departement_id)
            .all()
        )
        admins_by_department = {
            row.departement_id: {"email": row.email, "count": int(row.count or 0)}
            for row in active_admins
        }

        return [
            {
                "id": item.id,
                "nom_departement": item.nom_departement,
                "admin_attribue": admins_by_department.get(item.id, {}).get("count", 0) > 0,
                "administrateur_actif_email": admins_by_department.get(item.id, {}).get("email"),
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
        droits_by_name = self._ensure_business_droits()
        return [
            self._serialize_droit(droits_by_name[nom_droit])
            for nom_droit in BUSINESS_PERMISSION_LABELS
        ]

    def create_droit(self, nom_droit: str, admin_user: Utilisateur):
        nom = self._validate_business_droit_name(nom_droit)

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
                "label": BUSINESS_PERMISSION_LABELS.get(droit.nom_droit, droit.nom_droit),
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

        self._ensure_business_droits()
        self._cleanup_invalid_department_rights(departement)

        relations = (
            self.db.query(DepartementDroit)
            .options(selectinload(DepartementDroit.droit_acces))
            .filter(DepartementDroit.departement_id == departement.id)
            .all()
        )
        droits = [
            relation.droit_acces
            for relation in relations
            if relation.droit_acces
            and relation.droit_acces.nom_droit in valid_business_permissions()
        ]

        droits.sort(key=lambda item: self._business_permission_order(item.nom_droit))

        return {
            "departement_nom": departement.nom_departement,
            "droits": [self._serialize_droit(droit) for droit in droits],
        }

    def assign_rights_to_departement_by_nom(
        self,
        nom_departement: str,
        droit_noms: list[str],
        admin_user: Utilisateur,
    ):
        departement = self._get_departement_by_nom(nom_departement)

        droit_noms_clean = sorted(
            {self._validate_business_droit_name(item) for item in droit_noms if self._clean_name(item)},
            key=self._business_permission_order,
        )
        droits_by_name = self._ensure_business_droits()
        droits = [droits_by_name[nom_droit] for nom_droit in droit_noms_clean]

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
        nom = self._validate_business_droit_name(nom_droit)
        droit = self._ensure_business_droits()[nom]

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
        nom = self._validate_business_droit_name(nom_droit)
        droit = self._ensure_business_droits()[nom]

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

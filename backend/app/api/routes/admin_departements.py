from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_super_admin
from app.db.database import get_db
from app.models.utilisateur import Utilisateur
from app.schemas.admin_departements import (
    AdminAssignRightsToDepartementRequest,
    AdminCreateDepartementRequest,
    AdminCreateDroitRequest,
    AdminDepartementDeleteResponse,
    AdminDepartementResponse,
    AdminDepartmentRightsResponse,
    AdminDroitResponse,
)
from app.services.admin_departements_service import AdminDepartementsService

router = APIRouter(prefix="/admin", tags=["Admin - Départements et permissions"])


def get_admin_departements_service(
    db: Session = Depends(get_db),
) -> AdminDepartementsService:
    return AdminDepartementsService(db)


@router.get("/departements", response_model=list[AdminDepartementResponse])
def list_departements(
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.list_departements()


@router.post("/departements", response_model=AdminDepartementResponse)
def create_departement(
    payload: AdminCreateDepartementRequest,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.create_departement(payload.nom_departement, current_user)


@router.delete(
    "/departements/by-name/{nom_departement}",
    response_model=AdminDepartementDeleteResponse,
)
def delete_departement_by_nom(
    nom_departement: str,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.delete_departement_by_nom(
        nom_departement=nom_departement,
        admin_user=current_user,
    )


@router.get("/droits", response_model=list[AdminDroitResponse])
def list_droits(
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.list_droits()


@router.post("/droits", response_model=AdminDroitResponse)
def create_droit(
    payload: AdminCreateDroitRequest,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.create_droit(payload.nom_droit, current_user)


@router.get(
    "/departements/by-name/{nom_departement}/droits",
    response_model=AdminDepartmentRightsResponse,
)
def get_department_rights_by_nom(
    nom_departement: str,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.get_department_rights_by_nom(nom_departement)


@router.put(
    "/departements/by-name/{nom_departement}/droits",
    response_model=AdminDepartmentRightsResponse,
)
def assign_rights_to_departement_by_nom(
    nom_departement: str,
    payload: AdminAssignRightsToDepartementRequest,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.assign_rights_to_departement_by_nom(
        nom_departement=nom_departement,
        droit_noms=payload.droit_noms,
        admin_user=current_user,
    )


@router.post(
    "/departements/by-name/{nom_departement}/droits/{nom_droit:path}",
    response_model=AdminDepartmentRightsResponse,
)
def grant_right_to_departement_by_nom(
    nom_departement: str,
    nom_droit: str,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.grant_right_to_departement_by_nom(
        nom_departement=nom_departement,
        nom_droit=nom_droit,
        admin_user=current_user,
    )


@router.delete(
    "/departements/by-name/{nom_departement}/droits/{nom_droit:path}",
    response_model=AdminDepartmentRightsResponse,
)
def revoke_right_from_departement_by_nom(
    nom_departement: str,
    nom_droit: str,
    current_user: Utilisateur = Depends(require_super_admin),
    service: AdminDepartementsService = Depends(get_admin_departements_service),
):
    return service.revoke_right_from_departement_by_nom(
        nom_departement=nom_departement,
        nom_droit=nom_droit,
        admin_user=current_user,
    )

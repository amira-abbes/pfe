from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin_or_super_admin
from app.db.database import get_db
from app.models.utilisateur import Utilisateur
from app.schemas.admin import (
    AdminCreateUserRequest,
    AdminCreateUserResponse,
    AdminUpdateUserProfileRequest,
    AdminUpdateUserStatusRequest,
    AdminUserDetailResponse,
    AdminUserListItem,
    SimpleAdminMessageResponse,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["Admin - Utilisateurs"])


def get_admin_service(db: Session = Depends(get_db)) -> AdminService:
    return AdminService(db)


@router.post("/users", response_model=AdminCreateUserResponse)
def create_user(
    payload: AdminCreateUserRequest,
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.create_user(
        email=str(payload.email),
        nom_complet=payload.nom_complet,
        departement_nom=payload.departement_nom,
        role=payload.role or "USER",
        admin_user=current_user,
    )


@router.get("/users", response_model=list[AdminUserListItem])
def list_users(
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.list_users(current_user)


@router.get("/users/by-email/{email:path}", response_model=AdminUserDetailResponse)
def get_user_detail_by_email(
    email: str,
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.get_user_detail_by_email(email, current_user)


@router.patch("/users/by-email/{email:path}/status", response_model=SimpleAdminMessageResponse)
def update_user_status_by_email(
    email: str,
    payload: AdminUpdateUserStatusRequest,
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.update_user_status_by_email(
        email=email,
        est_actif=payload.est_actif,
        admin_user=current_user,
    )


@router.patch("/users/by-email/{email:path}/profile", response_model=SimpleAdminMessageResponse)
def update_user_profile_by_email(
    email: str,
    payload: AdminUpdateUserProfileRequest,
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.update_user_profile_by_email(
        email=email,
        departement_nom=payload.departement_nom,
        role=payload.role,
        admin_user=current_user,
    )


@router.delete("/users/by-email/{email:path}", response_model=SimpleAdminMessageResponse)
def delete_user_by_email(
    email: str,
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.delete_user_by_email(
        email=email,
        admin_user=current_user,
    )


@router.post("/users/by-email/{email:path}/recovery-codes/regenerate", response_model=SimpleAdminMessageResponse)
def regenerate_user_recovery_codes_by_email(
    email: str,
    current_user: Utilisateur = Depends(require_admin_or_super_admin),
    service: AdminService = Depends(get_admin_service),
):
    return service.regenerate_user_recovery_codes_by_email(
        email=email,
        admin_user=current_user,
    )

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    nom_complet: str = Field(min_length=2, max_length=150)
    departement_nom: Optional[str] = Field(default=None, max_length=100)
    role: Optional[str] = None


class AdminCreateUserResponse(BaseModel):
    utilisateur_id: UUID
    email: EmailStr
    nom_complet: str
    departement_nom: str
    role: str
    statut_compte: str
    est_actif: bool
    activation_email_sent: bool
    activation_link_debug: Optional[str] = None
    message: str


class AdminUpdateUserStatusRequest(BaseModel):
    est_actif: bool


class AdminUpdateUserProfileRequest(BaseModel):
    departement_nom: Optional[str] = Field(default=None, max_length=100)
    role: Optional[str] = None


class AdminUserListItem(BaseModel):
    id: UUID
    email: EmailStr
    nom_complet: str
    est_actif: bool
    role: str
    statut_compte: str
    departement_nom: Optional[str] = None
    date_creation: datetime
    date_derniere_connexion: Optional[datetime] = None
    date_desactivation: Optional[datetime] = None
    date_suppression: Optional[datetime] = None


class AdminUserDetailResponse(BaseModel):
    id: UUID
    email: EmailStr
    nom_complet: str
    est_actif: bool
    role: str
    statut_compte: str
    departement_nom: Optional[str] = None
    date_creation: datetime
    date_modification: datetime
    date_derniere_connexion: Optional[datetime] = None
    date_dernier_changement_mot_de_passe: Optional[datetime] = None
    date_desactivation: Optional[datetime] = None
    date_suppression: Optional[datetime] = None
    cree_par: Optional[UUID] = None


class SimpleAdminMessageResponse(BaseModel):
    success: bool = True
    message: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    departement_nom: Optional[str] = None

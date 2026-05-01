from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class AdminCreateDepartementRequest(BaseModel):
    nom_departement: str = Field(min_length=2, max_length=100)


class AdminDepartementResponse(BaseModel):
    id: UUID
    nom_departement: str


class AdminCreateDroitRequest(BaseModel):
    nom_droit: str = Field(min_length=2, max_length=150)


class AdminDroitResponse(BaseModel):
    id: UUID
    nom_droit: str


class AdminAssignRightsToDepartementRequest(BaseModel):
    droit_noms: List[str]


class AdminDepartmentRightItem(BaseModel):
    id: UUID
    nom_droit: str


class AdminDepartmentRightsResponse(BaseModel):
    departement_nom: str
    droits: List[AdminDepartmentRightItem]


class AdminDepartementDeleteResponse(BaseModel):
    success: bool = True
    message: str
    nom_departement: str

from datetime import timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.constants import (
    AUDIT_ADMIN_SESSION_EXPIRED,
    AUDIT_SESSION_ACTIVITY_UPDATED,
    AUDIT_USER_SESSION_EXPIRED,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    SESSION_ACTIVE,
    SESSION_EXPIRED,
)
from app.core.security import (
    decode_access_token,
    ensure_aware_utc,
    hash_session_token,
    utc_now,
)
from app.db.database import get_db
from app.models.departement import Departement
from app.models.departement_droit import DepartementDroit
from app.models.journal_audit import JournalAudit
from app.models.session_utilisateur import SessionUtilisateur
from app.models.utilisateur import Utilisateur

security_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Utilisateur:
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalide ou expirée.",
        )

    user_id = payload.get("sub")
    raw_session_token = payload.get("session_token")

    if not user_id or not raw_session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalide.",
        )

    session_hash = hash_session_token(raw_session_token)

    session = (
        db.query(SessionUtilisateur)
        .filter(SessionUtilisateur.utilisateur_id == user_id)
        .filter(SessionUtilisateur.jeton_session_hash == session_hash)
        .filter(SessionUtilisateur.revoque_a.is_(None))
        .filter(SessionUtilisateur.statut_session == SESSION_ACTIVE)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée. Veuillez vous reconnecter.",
        )

    now = utc_now()
    expire_a = ensure_aware_utc(session.expire_a)
    derniere_activite_a = ensure_aware_utc(session.derniere_activite_a)

    if expire_a and expire_a <= now:
        _expire_session(
            db=db,
            session=session,
            reason="Expiration absolue de session",
            role=session.role,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée. Veuillez vous reconnecter.",
        )

    inactivity_limit = (
        timedelta(minutes=settings.ADMIN_SESSION_IDLE_MINUTES)
        if str(session.role or "").upper() in {ROLE_ADMIN, ROLE_SUPER_ADMIN}
        else timedelta(minutes=settings.USER_SESSION_IDLE_MINUTES)
    )

    if derniere_activite_a and derniere_activite_a + inactivity_limit <= now:
        _expire_session(
            db=db,
            session=session,
            reason="Expiration par inactivité",
            role=session.role,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée. Veuillez vous reconnecter.",
        )

    user = (
        db.query(Utilisateur)
        .options(
            selectinload(Utilisateur.departement)
            .selectinload(Departement.departement_droits)
            .selectinload(DepartementDroit.droit_acces)
        )
        .filter(Utilisateur.id == user_id)
        .filter(Utilisateur.date_suppression.is_(None))
        .first()
    )

    if not user or not user.est_actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte indisponible.",
        )

    session.derniere_activite_a = now
    db.add(session)

    db.add(
        JournalAudit(
            utilisateur_acteur_id=user.id,
            cible_utilisateur_id=user.id,
            action_effectuee=AUDIT_SESSION_ACTIVITY_UPDATED,
            niveau_risque="FAIBLE",
            details={"role": session.role},
        )
    )

    db.commit()
    db.refresh(user)

    return user


def _expire_session(
    db: Session,
    session: SessionUtilisateur,
    reason: str,
    role: str,
) -> None:
    now = utc_now()

    session.revoque_a = now
    session.raison_revocation = reason
    session.statut_session = SESSION_EXPIRED

    action = (
        AUDIT_ADMIN_SESSION_EXPIRED
        if str(role or "").upper() in {ROLE_ADMIN, ROLE_SUPER_ADMIN}
        else AUDIT_USER_SESSION_EXPIRED
    )

    db.add(session)
    db.add(
        JournalAudit(
            utilisateur_acteur_id=session.utilisateur_id,
            cible_utilisateur_id=session.utilisateur_id,
            action_effectuee=action,
            niveau_risque="MOYEN",
            details={"reason": reason},
        )
    )
    db.commit()


def get_user_permissions(user: Utilisateur) -> list[str]:
    permissions: list[str] = []

    if not user.departement:
        return permissions

    for item in user.departement.departement_droits:
        if item.droit_acces and item.droit_acces.nom_droit:
            permissions.append(item.droit_acces.nom_droit)

    return permissions


def require_permission(permission: str):
    def checker(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
        role = str(current_user.role or "").upper()
        if role not in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "forbidden", "message": "Accès refusé."},
            )

        if role == ROLE_SUPER_ADMIN:
            return current_user

        permissions = get_user_permissions(current_user)

        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "forbidden", "message": "Accès refusé."},
            )

        return current_user

    return checker


def require_admin_or_super_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    if str(current_user.role or "").upper() not in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "forbidden", "message": "Accès refusé."},
        )
    return current_user


def require_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    return require_admin_or_super_admin(current_user)


def require_super_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    if str(current_user.role or "").upper() != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "forbidden", "message": "Accès refusé."},
        )
    return current_user


def require_department_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    if str(current_user.role or "").upper() != ROLE_ADMIN or not current_user.departement_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "forbidden", "message": "Accès refusé."},
        )
    return current_user


def require_current_active_user(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    if not current_user.est_actif or current_user.date_suppression is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "forbidden", "message": "Compte indisponible."},
        )
    return current_user

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.constants import ROLE_SUPER_ADMIN, SESSION_REVOKED, STATUT_ACTIVE
from app.core.security import utc_now
from app.db.database import SessionLocal
from app.models.session_utilisateur import SessionUtilisateur
from app.models.tentative_connexion import TentativeConnexion
from app.models.utilisateur import Utilisateur


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unblock local SUPER_ADMIN accounts without changing MFA or passwords."
    )
    parser.add_argument(
        "--email",
        help="Optional SUPER_ADMIN email to unblock. If omitted, all SUPER_ADMIN accounts are unblocked.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without committing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    email = str(args.email or "").strip().lower()
    now = utc_now()

    db = SessionLocal()
    try:
        query = db.query(Utilisateur).filter(Utilisateur.role == ROLE_SUPER_ADMIN)
        if email:
            query = query.filter(Utilisateur.email == email)

        super_admins = query.order_by(Utilisateur.date_creation.asc()).all()
        if not super_admins:
            target = f" avec l'email {email}" if email else ""
            print(f"Aucun compte SUPER_ADMIN{target} trouve.")
            return 1

        changed_users = 0
        deleted_attempts_total = 0
        revoked_sessions_total = 0

        for user in super_admins:
            role = str(user.role or "").upper()
            if role != ROLE_SUPER_ADMIN:
                print(f"Compte ignore par securite: {user.email} role={user.role}")
                continue

            deleted_attempts = (
                db.query(TentativeConnexion)
                .filter(TentativeConnexion.utilisateur_id == user.id)
                .delete(synchronize_session=False)
            )

            revoked_sessions = (
                db.query(SessionUtilisateur)
                .filter(SessionUtilisateur.utilisateur_id == user.id)
                .filter(SessionUtilisateur.revoque_a.is_(None))
                .update(
                    {
                        "revoque_a": now,
                        "raison_revocation": "Deblocage local SUPER_ADMIN",
                        "statut_session": SESSION_REVOKED,
                    },
                    synchronize_session=False,
                )
            )

            user.est_actif = True
            user.statut_compte = STATUT_ACTIVE
            user.date_desactivation = None

            user.nombre_echecs_password = 0
            user.nombre_echecs_totp = 0
            user.blocage_password_jusqu_a = None
            user.blocage_totp_jusqu_a = None

            user.password_lockout_requires_mail_action = False
            user.password_lockout_resolved_at = now
            user.password_lockout_mail_sent_at = None
            user.password_lockout_mail_expires_at = None

            user.recovery_code_failed_attempts = 0
            user.recovery_code_last_failure_at = None
            user.recovery_code_cooldown_until = None
            user.recovery_code_warning_sent_at = None
            user.recovery_code_alert_sent_at = None
            user.recovery_secure_link_required = False
            user.recovery_secure_link_expires_at = None

            user.date_derniere_alerte_securite = None
            user.date_modification = now
            db.add(user)

            changed_users += 1
            deleted_attempts_total += int(deleted_attempts or 0)
            revoked_sessions_total += int(revoked_sessions or 0)

            print(
                "SUPER_ADMIN prepare: "
                f"{user.email} | tentatives supprimees={deleted_attempts} "
                f"| sessions revoquees={revoked_sessions}"
            )

        if args.dry_run:
            db.rollback()
            print("Dry-run termine: aucun changement committe.")
            return 0

        db.commit()
        print(
            "Deblocage SUPER_ADMIN termine avec succes: "
            f"comptes={changed_users}, "
            f"tentatives supprimees={deleted_attempts_total}, "
            f"sessions revoquees={revoked_sessions_total}."
        )
        print("MFA et mot de passe inchanges.")
        return 0

    except Exception as exc:
        db.rollback()
        print(f"Erreur pendant le deblocage SUPER_ADMIN: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

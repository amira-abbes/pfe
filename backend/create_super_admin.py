from app.core.constants import ROLE_SUPER_ADMIN, STATUT_ACTIVE
from app.core.security import hash_password, utc_now
from app.db.database import SessionLocal
from app.models.utilisateur import Utilisateur


SUPER_ADMIN_EMAIL = "plateforme.tt.systemeadmin@gmail.com"
SUPER_ADMIN_PASSWORD = "SuperAdmin@2026!"
SUPER_ADMIN_NAME = "Super Administrateur Plateforme"


def main() -> None:
    db = SessionLocal()
    try:
        now = utc_now()
        user = (
            db.query(Utilisateur)
            .filter(Utilisateur.email == SUPER_ADMIN_EMAIL)
            .first()
        )

        if user is None:
            user = Utilisateur(
                email=SUPER_ADMIN_EMAIL,
                nom_complet=SUPER_ADMIN_NAME,
                role=ROLE_SUPER_ADMIN,
                est_actif=True,
                statut_compte=STATUT_ACTIVE,
                mot_de_passe_hash=hash_password(SUPER_ADMIN_PASSWORD),
                nombre_echecs_password=0,
                nombre_echecs_totp=0,
                blocage_password_jusqu_a=None,
                blocage_totp_jusqu_a=None,
                webauthn_admin_active=False,
                date_creation=now,
                date_modification=now,
            )
            db.add(user)
            action = "créé"
        else:
            user.nom_complet = SUPER_ADMIN_NAME
            user.role = ROLE_SUPER_ADMIN
            user.est_actif = True
            user.statut_compte = STATUT_ACTIVE
            user.mot_de_passe_hash = hash_password(SUPER_ADMIN_PASSWORD)
            user.nombre_echecs_password = 0
            user.nombre_echecs_totp = 0
            user.blocage_password_jusqu_a = None
            user.blocage_totp_jusqu_a = None
            user.password_lockout_resolved_at = None
            user.password_lockout_mail_sent_at = None
            user.password_lockout_mail_expires_at = None
            user.password_lockout_requires_mail_action = False
            user.recovery_code_failed_attempts = 0
            user.recovery_code_last_failure_at = None
            user.recovery_code_cooldown_until = None
            user.recovery_code_warning_sent_at = None
            user.recovery_code_alert_sent_at = None
            user.webauthn_admin_active = False
            user.date_desactivation = None
            user.date_suppression = None
            user.date_modification = now
            db.add(user)
            action = "mis à jour"

        db.commit()
        print(f"Compte SUPER_ADMIN {action} : {SUPER_ADMIN_EMAIL}")
        print("Mot de passe temporaire configuré. Aucun hash n'est affiché.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

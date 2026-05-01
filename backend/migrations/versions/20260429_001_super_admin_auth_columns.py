"""add super admin role and auth state columns

Revision ID: 20260429_001
Revises: 20260428_001
Create Date: 2026-04-29
"""

from alembic import op

revision = "20260429_001"
down_revision = "20260428_001"
branch_labels = None
depends_on = None


RESET_TOKEN_TYPES = (
    "PASSWORD_RESET",
    "PASSWORD_RESET_FROM_LOCKOUT",
    "RESET_PASSWORD_RECOVERY_CODE",
    "SECURITY_REPORT",
    "MFA_BACKUP_CODE",
    "MFA_RESET",
    "MFA_SETUP",
    "RECOVERY_CODE_ASSISTANCE",
)


def _values(items: tuple[str, ...]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.utilisateurs
        DROP CONSTRAINT IF EXISTS chk_utilisateurs_role
        """
    )
    op.execute(
        """
        ALTER TABLE app.utilisateurs
        ADD CONSTRAINT chk_utilisateurs_role
        CHECK (role IN ('USER', 'ADMIN', 'SUPER_ADMIN'))
        """
    )

    op.execute(
        """
        ALTER TABLE app.utilisateurs
            ADD COLUMN IF NOT EXISTS password_lockout_resolved_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS password_lockout_mail_sent_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS password_lockout_mail_expires_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS password_lockout_requires_mail_action BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS recovery_code_failed_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS recovery_code_last_failure_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS recovery_code_cooldown_until TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS recovery_code_warning_sent_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS recovery_code_alert_sent_at TIMESTAMPTZ NULL
        """
    )

    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
            ADD COLUMN IF NOT EXISTS mfa_dernier_echec_a TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS mfa_cooldown_jusqu_a TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS mfa_recovery_bloque_jusqu_a TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS mfa_echecs_totp INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS mfa_totp_bloque BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS mfa_echecs_recovery INTEGER NOT NULL DEFAULT 0
        """
    )

    values = _values(RESET_TOKEN_TYPES)
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_token
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_token
        CHECK (type_token IS NULL OR type_token IN ({values}))
        """
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_jeton
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_jeton
        CHECK (type_jeton IN ({values}))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.utilisateurs
        DROP CONSTRAINT IF EXISTS chk_utilisateurs_role
        """
    )
    op.execute(
        """
        ALTER TABLE app.utilisateurs
        ADD CONSTRAINT chk_utilisateurs_role
        CHECK (role IN ('USER', 'ADMIN'))
        """
    )

    op.execute(
        """
        ALTER TABLE app.utilisateurs
            DROP COLUMN IF EXISTS password_lockout_resolved_at,
            DROP COLUMN IF EXISTS password_lockout_mail_sent_at,
            DROP COLUMN IF EXISTS password_lockout_mail_expires_at,
            DROP COLUMN IF EXISTS password_lockout_requires_mail_action,
            DROP COLUMN IF EXISTS recovery_code_failed_attempts,
            DROP COLUMN IF EXISTS recovery_code_last_failure_at,
            DROP COLUMN IF EXISTS recovery_code_cooldown_until,
            DROP COLUMN IF EXISTS recovery_code_warning_sent_at,
            DROP COLUMN IF EXISTS recovery_code_alert_sent_at
        """
    )

    old_values = _values(
        (
            "PASSWORD_RESET",
            "PASSWORD_RESET_FROM_LOCKOUT",
            "RESET_PASSWORD_RECOVERY_CODE",
            "MFA_BACKUP_CODE",
            "MFA_RESET",
            "SECURITY_REPORT",
        )
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_token
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_token
        CHECK (type_token IS NULL OR type_token IN ({old_values}))
        """
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_jeton
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_jeton
        CHECK (type_jeton IN ({old_values}))
        """
    )

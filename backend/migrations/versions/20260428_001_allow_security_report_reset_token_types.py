"""allow security report reset token types

Revision ID: 20260428_001
Revises:
Create Date: 2026-04-28
"""

from alembic import op

revision = "20260428_001"
down_revision = None
branch_labels = None
depends_on = None

ALLOWED_TYPES = (
    "PASSWORD_RESET",
    "PASSWORD_RESET_FROM_LOCKOUT",
    "RESET_PASSWORD_RECOVERY_CODE",
    "MFA_BACKUP_CODE",
    "MFA_RESET",
    "SECURITY_REPORT",
)


def _allowed_values_sql() -> str:
    return ", ".join(f"'{value}'" for value in ALLOWED_TYPES)


def upgrade() -> None:
    values = _allowed_values_sql()
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
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_token
        """
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_token
        CHECK (
            type_token IS NULL OR type_token IN (
                'PASSWORD_RESET',
                'PASSWORD_RESET_FROM_LOCKOUT'
            )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_jeton
        """
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_jeton
        CHECK (
            type_jeton IN (
                'PASSWORD_RESET',
                'PASSWORD_RESET_FROM_LOCKOUT'
            )
        )
        """
    )

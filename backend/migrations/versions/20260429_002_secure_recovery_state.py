"""add secure recovery state

Revision ID: 20260429_002
Revises: 20260429_001
Create Date: 2026-04-29
"""

from alembic import op

revision = "20260429_002"
down_revision = "20260429_001"
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
    "SUPER_ADMIN_SECURE_RECOVERY_24H",
)


def _values(items: tuple[str, ...]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.utilisateurs
            ADD COLUMN IF NOT EXISTS recovery_secure_link_required BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS recovery_secure_link_expires_at TIMESTAMPTZ NULL
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
            DROP COLUMN IF EXISTS recovery_secure_link_required,
            DROP COLUMN IF EXISTS recovery_secure_link_expires_at
        """
    )

"""merge ELT result permission into treatment permission

Revision ID: 20260617_001
Revises: 20260616_003
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa

revision = "20260617_001"
down_revision = "20260616_003"
branch_labels = None
depends_on = None


BUSINESS_RIGHTS = (
    "voir_dashboard_service_sos",
    "voir_dashboard_parc_service_sos",
    "voir_dashboard_bad_debts",
    "lancer_traitement_elt",
)
LEGACY_ELT_RIGHT = "voir_resultat_elt"


def _right_id(connection, name: str):
    return connection.execute(
        sa.text("SELECT id FROM app.droits_acces WHERE nom_droit = :name"),
        {"name": name},
    ).scalar_one()


def _department_ids(connection, condition: str):
    return [
        row[0]
        for row in connection.execute(
            sa.text(f"SELECT id FROM app.departements WHERE {condition}")
        ).all()
    ]


def _replace_department_rights(connection, department_ids, right_names):
    if not department_ids:
        return

    business_right_ids = [_right_id(connection, name) for name in BUSINESS_RIGHTS]
    next_right_ids = [_right_id(connection, name) for name in right_names]

    for department_id in department_ids:
        for right_id in business_right_ids:
            connection.execute(
                sa.text(
                    """
                    DELETE FROM app.departement_droits
                    WHERE departement_id = :department_id
                      AND droit_acces_id = :right_id
                    """
                ),
                {"department_id": department_id, "right_id": right_id},
            )
        for right_id in next_right_ids:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO app.departement_droits (departement_id, droit_acces_id)
                    VALUES (:department_id, :right_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"department_id": department_id, "right_id": right_id},
            )


def upgrade() -> None:
    connection = op.get_bind()

    for right_name in BUSINESS_RIGHTS:
        connection.execute(
            sa.text(
                """
                INSERT INTO app.droits_acces (id, nom_droit)
                VALUES (gen_random_uuid(), :name)
                ON CONFLICT (nom_droit) DO NOTHING
                """
            ),
            {"name": right_name},
        )

    legacy_id = connection.execute(
        sa.text("SELECT id FROM app.droits_acces WHERE nom_droit = :name"),
        {"name": LEGACY_ELT_RIGHT},
    ).scalar_one_or_none()
    target_id = _right_id(connection, "lancer_traitement_elt")

    if legacy_id:
        connection.execute(
            sa.text(
                """
                INSERT INTO app.departement_droits (departement_id, droit_acces_id)
                SELECT departement_id, :target_id
                FROM app.departement_droits
                WHERE droit_acces_id = :legacy_id
                ON CONFLICT DO NOTHING
                """
            ),
            {"target_id": target_id, "legacy_id": legacy_id},
        )
        connection.execute(
            sa.text("DELETE FROM app.departement_droits WHERE droit_acces_id = :legacy_id"),
            {"legacy_id": legacy_id},
        )
        connection.execute(
            sa.text("DELETE FROM app.droits_acces WHERE id = :legacy_id"),
            {"legacy_id": legacy_id},
        )

    _replace_department_rights(
        connection,
        _department_ids(connection, "lower(nom_departement) LIKE '%commercial%'"),
        ("voir_dashboard_bad_debts",),
    )
    _replace_department_rights(
        connection,
        _department_ids(
            connection,
            "lower(nom_departement) IN ('assurance', 'assurance risque', 'assurance et risque')",
        ),
        ("voir_dashboard_service_sos", "voir_dashboard_parc_service_sos"),
    )
    _replace_department_rights(
        connection,
        _department_ids(
            connection,
            """
            lower(nom_departement) LIKE '%analyse%'
            AND (
                lower(nom_departement) LIKE '%operation%'
                OR lower(nom_departement) LIKE '%opération%'
            )
            """,
        ),
        (
            "voir_dashboard_service_sos",
            "voir_dashboard_parc_service_sos",
            "lancer_traitement_elt",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO app.droits_acces (id, nom_droit)
            VALUES (gen_random_uuid(), :name)
            ON CONFLICT (nom_droit) DO NOTHING
            """
        ),
        {"name": LEGACY_ELT_RIGHT},
    )

    _replace_department_rights(
        connection,
        _department_ids(
            connection,
            """
            lower(nom_departement) LIKE '%analyse%'
            AND (
                lower(nom_departement) LIKE '%operation%'
                OR lower(nom_departement) LIKE '%opération%'
            )
            """,
        ),
        (
            "voir_dashboard_service_sos",
            "voir_dashboard_parc_service_sos",
            "lancer_traitement_elt",
        ),
    )

from types import SimpleNamespace
import unittest

from app.core.access_control import user_effective_permissions
from app.core.constants import (
    PERMISSION_DASHBOARD_BAD_DEBTS,
    PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
    PERMISSION_DASHBOARD_SERVICE_SOS,
    PERMISSION_LANCER_ELT,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
)


def make_user(role, business_permissions):
    relations = [
        SimpleNamespace(droit_acces=SimpleNamespace(nom_droit=name))
        for name in business_permissions
    ]
    department = SimpleNamespace(
        nom_departement="Analyse Operationnelle",
        departement_droits=relations,
    )
    return SimpleNamespace(role=role, departement=department)


class EffectiveDepartmentPermissionsTest(unittest.TestCase):
    def test_admin_and_user_inherit_the_same_department_permissions(self):
        business_permissions = [
            "voir_dashboard_service_sos",
            "lancer_traitement_elt",
        ]

        expected = {
            PERMISSION_DASHBOARD_SERVICE_SOS,
            PERMISSION_LANCER_ELT,
        }

        self.assertEqual(user_effective_permissions(make_user(ROLE_ADMIN, business_permissions)), expected)
        self.assertEqual(user_effective_permissions(make_user(ROLE_USER, business_permissions)), expected)

    def test_revoked_department_permission_is_not_effective(self):
        user = make_user(ROLE_USER, ["voir_dashboard_parc_service_sos"])

        permissions = user_effective_permissions(user)

        self.assertIn(PERMISSION_DASHBOARD_PARC_SERVICE_SOS, permissions)
        self.assertNotIn(PERMISSION_DASHBOARD_SERVICE_SOS, permissions)
        self.assertNotIn(PERMISSION_LANCER_ELT, permissions)

    def test_each_visible_module_permission_can_be_revoked_and_reactivated(self):
        permission_pairs = [
            ("voir_dashboard_service_sos", PERMISSION_DASHBOARD_SERVICE_SOS),
            ("voir_dashboard_parc_service_sos", PERMISSION_DASHBOARD_PARC_SERVICE_SOS),
            ("voir_dashboard_bad_debts", PERMISSION_DASHBOARD_BAD_DEBTS),
            ("lancer_traitement_elt", PERMISSION_LANCER_ELT),
        ]

        for business_permission, effective_permission in permission_pairs:
            with self.subTest(permission=business_permission):
                self.assertNotIn(
                    effective_permission,
                    user_effective_permissions(make_user(ROLE_USER, [])),
                )
                self.assertIn(
                    effective_permission,
                    user_effective_permissions(make_user(ROLE_USER, [business_permission])),
                )

    def test_reactivated_permission_becomes_effective(self):
        user = make_user(ROLE_ADMIN, ["voir_dashboard_bad_debts"])

        self.assertEqual(user_effective_permissions(user), {PERMISSION_DASHBOARD_BAD_DEBTS})

    def test_legacy_elt_result_permission_maps_to_treatment_access(self):
        user = make_user(ROLE_USER, ["voir_resultat_elt"])

        self.assertEqual(user_effective_permissions(user), {PERMISSION_LANCER_ELT})

    def test_super_admin_keeps_global_permissions(self):
        super_admin = SimpleNamespace(role=ROLE_SUPER_ADMIN, departement=None)

        permissions = user_effective_permissions(super_admin)

        self.assertIn(PERMISSION_DASHBOARD_SERVICE_SOS, permissions)
        self.assertIn(PERMISSION_DASHBOARD_PARC_SERVICE_SOS, permissions)
        self.assertIn(PERMISSION_DASHBOARD_BAD_DEBTS, permissions)
        self.assertIn(PERMISSION_LANCER_ELT, permissions)


if __name__ == "__main__":
    unittest.main()

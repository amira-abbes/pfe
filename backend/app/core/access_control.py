import unicodedata

from app.core.constants import (
    PERMISSION_DASHBOARD_BAD_DEBTS,
    PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
    PERMISSION_DASHBOARD_SERVICE_SOS,
    PERMISSION_GERER_DEPARTEMENTS,
    PERMISSION_GERER_ROLES,
    PERMISSION_GERER_UTILISATEURS,
    PERMISSION_LANCER_ELT,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
)


COMMERCIAL_DEPARTMENT = "COMMERCIAL"
RISK_DEPARTMENT = "ASSURANCE_RISQUE"
OPERATIONAL_ANALYSIS_DEPARTMENT = "ANALYSE_OPERATIONNELLE"
ROLE_ADMIN_DEPARTEMENTAL = "ADMIN_DEPARTEMENTAL"
DEPARTMENT_ADMIN_ROLES = {ROLE_ADMIN, ROLE_ADMIN_DEPARTEMENTAL}

BUSINESS_PERMISSION_DASHBOARD_SERVICE_SOS = "voir_dashboard_service_sos"
BUSINESS_PERMISSION_DASHBOARD_PARC_SERVICE_SOS = "voir_dashboard_parc_service_sos"
BUSINESS_PERMISSION_DASHBOARD_BAD_DEBTS = "voir_dashboard_bad_debts"
BUSINESS_PERMISSION_LANCER_TRAITEMENT_ELT = "lancer_traitement_elt"
BUSINESS_PERMISSION_VOIR_RESULTAT_ELT = "voir_resultat_elt"

BUSINESS_PERMISSION_LABELS = {
    BUSINESS_PERMISSION_DASHBOARD_SERVICE_SOS: "Dashboard Service SOS",
    BUSINESS_PERMISSION_DASHBOARD_PARC_SERVICE_SOS: "Dashboard Parc Service SOS",
    BUSINESS_PERMISSION_DASHBOARD_BAD_DEBTS: "Dashboard Bad Debts",
    BUSINESS_PERMISSION_LANCER_TRAITEMENT_ELT: "Lancer traitement ELT",
    BUSINESS_PERMISSION_VOIR_RESULTAT_ELT: "Voir résultat ELT",
}

BUSINESS_DEPARTMENT_PERMISSIONS = {
    COMMERCIAL_DEPARTMENT: {
        BUSINESS_PERMISSION_DASHBOARD_BAD_DEBTS,
    },
    RISK_DEPARTMENT: {
        BUSINESS_PERMISSION_DASHBOARD_SERVICE_SOS,
        BUSINESS_PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
        BUSINESS_PERMISSION_LANCER_TRAITEMENT_ELT,
        BUSINESS_PERMISSION_VOIR_RESULTAT_ELT,
    },
    OPERATIONAL_ANALYSIS_DEPARTMENT: {
        BUSINESS_PERMISSION_DASHBOARD_SERVICE_SOS,
        BUSINESS_PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
        BUSINESS_PERMISSION_LANCER_TRAITEMENT_ELT,
        BUSINESS_PERMISSION_VOIR_RESULTAT_ELT,
    },
}

SUPER_ADMIN_PERMISSIONS = {
    PERMISSION_GERER_UTILISATEURS,
    PERMISSION_GERER_DEPARTEMENTS,
    PERMISSION_GERER_ROLES,
    PERMISSION_DASHBOARD_SERVICE_SOS,
    PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
    PERMISSION_DASHBOARD_BAD_DEBTS,
    PERMISSION_LANCER_ELT,
}

DEPARTMENT_ADMIN_PERMISSIONS = {
    COMMERCIAL_DEPARTMENT: {
        PERMISSION_DASHBOARD_SERVICE_SOS,
        PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
    },
    RISK_DEPARTMENT: {
        PERMISSION_DASHBOARD_BAD_DEBTS,
    },
    OPERATIONAL_ANALYSIS_DEPARTMENT: {
        PERMISSION_DASHBOARD_SERVICE_SOS,
        PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
        PERMISSION_LANCER_ELT,
    },
}

DEPARTMENT_USER_PERMISSIONS = {
    COMMERCIAL_DEPARTMENT: {
        PERMISSION_DASHBOARD_BAD_DEBTS,
    },
    RISK_DEPARTMENT: {
        PERMISSION_DASHBOARD_SERVICE_SOS,
        PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
        PERMISSION_LANCER_ELT,
    },
    OPERATIONAL_ANALYSIS_DEPARTMENT: {
        PERMISSION_DASHBOARD_SERVICE_SOS,
        PERMISSION_DASHBOARD_PARC_SERVICE_SOS,
        PERMISSION_LANCER_ELT,
    },
}


def normalize_department_name(name: str | None) -> str:
    value = unicodedata.normalize("NFKD", str(name or "").strip().lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.replace("&", " et ").replace("-", " ").replace("_", " ").split())


def strip_department_prefix(normalized_name: str) -> str:
    if normalized_name.startswith("departement "):
        return normalized_name.removeprefix("departement ").strip()
    return normalized_name


def department_key(name: str | None) -> str | None:
    normalized = strip_department_prefix(normalize_department_name(name))
    words = set(normalized.split())

    if "commercial" in words:
        return COMMERCIAL_DEPARTMENT

    if normalized in {"assurance", "assurance risque", "assurance et risque"}:
        return RISK_DEPARTMENT

    has_analysis = "analyse" in words or "analyses" in words
    has_operational = (
        "operationnel" in words
        or "operationnelle" in words
        or "operationnels" in words
        or "operationnelles" in words
    )
    if has_analysis and has_operational:
        return OPERATIONAL_ANALYSIS_DEPARTMENT

    return None


def permissions_for_role_department(role: str | None, department_name: str | None) -> set[str]:
    normalized_role = str(role or "").upper()
    if normalized_role == ROLE_SUPER_ADMIN:
        return set(SUPER_ADMIN_PERMISSIONS)

    key = department_key(department_name)
    if normalized_role in DEPARTMENT_ADMIN_ROLES:
        return set(DEPARTMENT_ADMIN_PERMISSIONS.get(key, set()))

    if normalized_role == ROLE_USER:
        return set(DEPARTMENT_USER_PERMISSIONS.get(key, set()))

    return set()


def valid_business_permissions() -> set[str]:
    return set(BUSINESS_PERMISSION_LABELS)


def business_permissions_for_department(department_name: str | None) -> set[str]:
    key = department_key(department_name)
    return set(BUSINESS_DEPARTMENT_PERMISSIONS.get(key, set()))


def user_effective_permissions(user) -> set[str]:
    department_name = user.departement.nom_departement if getattr(user, "departement", None) else None
    return permissions_for_role_department(getattr(user, "role", None), department_name)


def user_has_permission(user, permission: str) -> bool:
    return permission in user_effective_permissions(user)

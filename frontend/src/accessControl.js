const SUPER_ADMIN_PERMISSIONS = [
  "gerer_utilisateurs",
  "gerer_departements",
  "gerer_roles",
  "dashboard_service_sos",
  "dashboard_parc_service_sos",
  "dashboard_bad_debts",
  "lancer_elt",
];

export const DEPARTMENT_KEYS = {
  COMMERCIAL: "COMMERCIAL",
  ASSURANCE_RISQUE: "ASSURANCE_RISQUE",
  ANALYSE_OPERATIONNELLE: "ANALYSE_OPERATIONNELLE",
};

const DEPARTMENT_ADMIN_PERMISSIONS = {
  [DEPARTMENT_KEYS.COMMERCIAL]: ["dashboard_service_sos", "dashboard_parc_service_sos"],
  [DEPARTMENT_KEYS.ASSURANCE_RISQUE]: ["dashboard_bad_debts"],
  [DEPARTMENT_KEYS.ANALYSE_OPERATIONNELLE]: ["dashboard_service_sos", "dashboard_parc_service_sos", "lancer_elt"],
};

const DEPARTMENT_USER_PERMISSIONS = {
  [DEPARTMENT_KEYS.COMMERCIAL]: ["dashboard_bad_debts"],
  [DEPARTMENT_KEYS.ASSURANCE_RISQUE]: ["dashboard_service_sos", "dashboard_parc_service_sos", "lancer_elt"],
  [DEPARTMENT_KEYS.ANALYSE_OPERATIONNELLE]: ["dashboard_service_sos", "dashboard_parc_service_sos", "lancer_elt"],
};

const DEPARTMENT_ADMIN_ROLES = new Set(["ADMIN", "ADMIN_DEPARTEMENTAL"]);

function normalizeDepartmentName(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&/g, " et ")
    .replace(/[-_]/g, " ")
    .replace(/\s+/g, " ");
}

function stripDepartmentPrefix(normalizedName) {
  return normalizedName.replace(/^departement\s+/, "").trim();
}

export function departmentKey(name) {
  const normalized = stripDepartmentPrefix(normalizeDepartmentName(name));
  const words = new Set(normalized.split(" ").filter(Boolean));

  if (words.has("commercial")) return DEPARTMENT_KEYS.COMMERCIAL;
  if (
    normalized === "assurance" ||
    normalized === "assurance risque" ||
    normalized === "assurance et risque"
  ) {
    return DEPARTMENT_KEYS.ASSURANCE_RISQUE;
  }

  const hasAnalysis = words.has("analyse") || words.has("analyses");
  const hasOperational =
    words.has("operationnel") ||
    words.has("operationnelle") ||
    words.has("operationnels") ||
    words.has("operationnelles");

  if (hasAnalysis && hasOperational) return DEPARTMENT_KEYS.ANALYSE_OPERATIONNELLE;
  return null;
}

export function effectivePermissionsForUser(user) {
  const role = String(user?.role || "").toUpperCase();
  if (role === "SUPER_ADMIN") return SUPER_ADMIN_PERMISSIONS;
  const key = departmentKey(user?.departement_nom);
  if (DEPARTMENT_ADMIN_ROLES.has(role)) {
    return DEPARTMENT_ADMIN_PERMISSIONS[key] || [];
  }
  if (role === "USER") {
    return DEPARTMENT_USER_PERMISSIONS[key] || [];
  }
  return [];
}

export function canAccessRight(user, right) {
  if (!right) return true;
  return effectivePermissionsForUser(user).includes(right);
}

export function firstAuthorizedPath(user) {
  const role = String(user?.role || "").toUpperCase();
  const permissions = effectivePermissionsForUser(user);

  if (role === "SUPER_ADMIN") return "/accueil";
  if (DEPARTMENT_ADMIN_ROLES.has(role)) {
    if (permissions.includes("dashboard_service_sos")) return "/dashboard/service-sos";
    if (permissions.includes("dashboard_bad_debts")) return "/dashboard/bad-debts";
    if (permissions.includes("dashboard_parc_service_sos")) return "/dashboard/parc-service-sos";
    if (permissions.includes("lancer_elt")) return "/admin/elt";
    return "/admin/mon-departement";
  }
  return "/accueil";
}

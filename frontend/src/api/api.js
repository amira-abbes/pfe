import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const LAST_ACTIVITY_KEY = "lastActivityAt";
const AUTH_FLOW_PREFIXES = [
  "/login",
  "/session-expired",
  "/auth",
  "/mfa",
  "/activation",
  "/forgot-password",
  "/password-reset",
  "/recovery-code",
  "/account-disabled",
];

let isRedirectingToLogin = false;
let isRedirectingToAccountDisabled = false;

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

const storedToken = localStorage.getItem("access_token");
if (storedToken) {
  api.defaults.headers.common.Authorization = `Bearer ${storedToken}`;
}

function isAuthFlowPath(pathname = window.location.pathname) {
  return AUTH_FLOW_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function clearStoredAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("current_user");
  localStorage.removeItem(LAST_ACTIVITY_KEY);
  delete api.defaults.headers.common.Authorization;
}

function emitAuthRedirect(to, reason) {
  window.dispatchEvent(
    new CustomEvent("auth:redirect", {
      detail: { to, reason },
    })
  );
}

function safeSpaRedirect(to, reason) {
  if (!to) return;
  emitAuthRedirect(to, reason);
}

function shouldRedirectFor401(error) {
  const config = error?.config || {};
  if (config.skipAuthRedirect === true || config.suppressAuthRedirect === true) return false;
  if (axios.isCancel?.(error) || error?.code === "ERR_CANCELED") return false;
  if (!error?.response) return false;
  if (isAuthFlowPath()) return false;

  const method = String(config.method || "get").toLowerCase();
  const url = String(config.url || "");
  if (method === "get" && !url.includes("/auth/me")) return false;

  return true;
}

function redirectToLoginOnce(reason = "auth_required") {
  if (isRedirectingToLogin || isAuthFlowPath()) return;
  isRedirectingToLogin = true;
  clearStoredAuth();
  safeSpaRedirect(`/login?reason=${encodeURIComponent(reason)}`, reason);
}

function redirectToAccountDisabledOnce(detailStatus, message) {
  if (isRedirectingToAccountDisabled || isAuthFlowPath()) return;
  isRedirectingToAccountDisabled = true;
  clearStoredAuth();
  const encodedMessage = encodeURIComponent(message || "Compte indisponible.");
  const accountStatus = encodeURIComponent(detailStatus || "account_unavailable");
  safeSpaRedirect(`/account-disabled?reason=${accountStatus}&message=${encodedMessage}`, detailStatus);
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => {
    if (String(response?.config?.url || "").includes("/auth/login")) {
      isRedirectingToLogin = false;
      isRedirectingToAccountDisabled = false;
    }
    return response;
  },
  (error) => {
    const status = error?.response?.status;
    const skipAuthRedirect =
      error?.config?.skipAuthRedirect === true ||
      error?.config?.suppressAuthRedirect === true;

    const detail = error?.response?.data?.detail;
    const detailStatus =
      detail && typeof detail === "object" ? String(detail.status || "") : "";
    const accountStatuses = new Set([
      "account_disabled",
      "account_blocked",
      "account_pending_first_login",
      "account_deleted",
      "account_unavailable",
    ]);

    if (status === 403 && accountStatuses.has(detailStatus) && !skipAuthRedirect) {
      redirectToAccountDisabledOnce(detailStatus, detail.message);
    }

    if (status === 401 && shouldRedirectFor401(error)) {
      redirectToLoginOnce("auth_required");
    }

    return Promise.reject(error);
  }
);

function mapValidationError(item) {
  const rawMessage = String(item?.msg || item?.message || "").toLowerCase();
  const type = String(item?.type || "").toLowerCase();
  const location = Array.isArray(item?.loc)
    ? item.loc.map((part) => String(part).toLowerCase()).join(".")
    : "";

  if (location.includes("code_secours") || location.includes("recovery_code")) {
    return "Format du code de secours invalide.";
  }

  if (type.includes("too_long") || rawMessage.includes("at most")) {
    return "Format invalide.";
  }

  if (type.includes("missing") || rawMessage.includes("field required")) {
    return "Champ obligatoire.";
  }

  if (
    rawMessage.includes("valid") ||
    rawMessage.includes("input should be") ||
    rawMessage.includes("validation")
  ) {
    return "Format invalide.";
  }

  return "Erreur de validation.";
}

export function getApiError(error, fallback = "Une erreur est survenue.") {
  const data = error?.response?.data;

  if (!error?.response) {
    return "Impossible de contacter le serveur. Vérifiez votre connexion ou réessayez.";
  }

  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (
    data?.detail &&
    typeof data.detail === "object" &&
    typeof data.detail.message === "string"
  ) {
    return data.detail.message;
  }

  if (Array.isArray(data?.detail)) {
    return [...new Set(data.detail.map(mapValidationError))].join(" ");
  }

  if (typeof data?.message === "string") {
    return data.message;
  }

  return fallback;
}

export function getBadDebtsSummary() {
  return api.get("/api/v1/bad-debts/metrics/summary");
}

export function getBadDebtsClients(params = {}) {
  return api.get("/api/v1/bad-debts/clients", { params });
}

export function getBadDebtsAtRisk(params = {}) {
  return api.get("/api/v1/bad-debts/clients/at-risk", { params });
}

export function getBadDebtsClientDetail(msisdn) {
  return api.get(`/api/v1/bad-debts/clients/${encodeURIComponent(msisdn)}`);
}

export function runBadDebtsAgent(msisdn) {
  return api.post(`/api/v1/bad-debts/clients/${encodeURIComponent(msisdn)}/run-agent`);
}

export function runBadDebtsAgentBatch(params = {}) {
  return api.post("/api/v1/bad-debts/agent/run-batch", null, { params });
}

export function getBadDebtsAgentReports(params = {}) {
  return api.get("/api/v1/bad-debts/agent/reports", { params });
}

export function getBadDebtsRecentActions(params = {}) {
  return api.get("/api/v1/bad-debts/actions/recent", { params });
}

export function getBadDebtsImportRuns(params = {}) {
  return api.get("/api/v1/bad-debts/import-runs", { params });
}

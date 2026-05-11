import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

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

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const skipAuthRedirect = error?.config?.skipAuthRedirect === true;

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
      localStorage.removeItem("access_token");
      localStorage.removeItem("current_user");
      localStorage.removeItem("lastActivityAt");
      delete api.defaults.headers.common.Authorization;
      const message = encodeURIComponent(detail.message || "Compte indisponible.");
      const accountStatus = encodeURIComponent(detailStatus);
      window.location.href = `/account-disabled?reason=${accountStatus}&message=${message}`;
    }

    if (status === 401 && !skipAuthRedirect) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("current_user");
      localStorage.removeItem("lastActivityAt");
      delete api.defaults.headers.common.Authorization;
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login?reason=auth_required";
      }
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

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { effectivePermissionsForUser } from "../accessControl";
import { api } from "../api/api";

const AuthContext = createContext(null);
const ACCOUNT_STATUS_CHECK_MS = 30 * 1000;
const PERMISSIONS_CHANGED_KEY = "permissionsChangedAt";
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

const MFA_SESSION_KEYS = [
  "mfa_token",
  "mfa_email",
  "mfa_role",
  "mfa_setup_token",
  "mfa_totp_cooldown",
];

const ADMIN_ROLES = ["ADMIN", "ADMIN_DEPARTEMENTAL", "SUPER_ADMIN"];

function readStoredUser() {
  const raw = localStorage.getItem("current_user");
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    localStorage.removeItem("current_user");
    return null;
  }
}

function dashboardForRole(role) {
  const normalizedRole = String(role || "USER").toUpperCase();
  if (ADMIN_ROLES.includes(normalizedRole)) return "/accueil";
  return "/user/dashboard";
}

function cleanupMfaSession() {
  MFA_SESSION_KEYS.forEach((key) => sessionStorage.removeItem(key));
}

function userHasRight(user, code) {
  if (!code) return true;
  return effectivePermissionsForUser(user).includes(code);
}

function isAuthFlowPath(pathname = window.location.pathname) {
  return AUTH_FLOW_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

async function stopEltWatchBestEffort() {
  try {
    await api.post("/elt/watch/stop", null, { skipAuthRedirect: true });
  } catch {
    // ignore: logout must never be blocked by ELT watcher cleanup
  }
}

function stopEltWatchOnUnload() {
  const token = localStorage.getItem("access_token");
  if (!token) return;

  const baseUrl = String(api.defaults.baseURL || "").replace(/\/$/, "");
  const url = `${baseUrl}/elt/watch/stop`;
  try {
    fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      keepalive: true,
    }).catch(() => {});
  } catch {
    // ignore
  }
}

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const accountStatusTimerRef = useRef(null);
  const redirectingRef = useRef(false);
  const [accessToken, setAccessToken] = useState(() =>
    localStorage.getItem("access_token")
  );
  const [user, setUser] = useState(() => readStoredUser());
  const [loading, setLoading] = useState(() => {
    const token = localStorage.getItem("access_token");
    return Boolean(token);
  });

  const isAuthenticated = Boolean(accessToken);
  const isAdmin = ADMIN_ROLES.includes(user?.role);
  const hasRight = (code) => userHasRight(user, code);

  function clearAccountStatusTimer() {
    window.clearInterval(accountStatusTimerRef.current);
    accountStatusTimerRef.current = null;
  }

  function navigateOnce(to, options = {}) {
    if (!to || redirectingRef.current) return;
    if (isAuthFlowPath(location.pathname) && isAuthFlowPath(to)) return;
    redirectingRef.current = true;
    navigate(to, { replace: options.replace !== false });
  }

  function saveLogin(token) {
    if (!token) {
      throw new Error("Token de connexion manquant.");
    }

    localStorage.setItem("access_token", token);
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
    setAccessToken(token);
  }

  function logoutLocal() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    delete api.defaults.headers.common.Authorization;
    clearAccountStatusTimer();
    setAccessToken(null);
    setUser(null);
    setLoading(false);
  }

  async function refreshMe(options = {}) {
    const token = localStorage.getItem("access_token");
    if (!token) return null;

    api.defaults.headers.common.Authorization = `Bearer ${token}`;
    if (!options.silent) {
      setLoading(true);
    }

    try {
      const response = await api.get("/auth/me", {
        skipAuthRedirect: options.skipAuthRedirect === true,
      });
      setUser(response.data);
      localStorage.setItem("current_user", JSON.stringify(response.data));
      return response.data;
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  }

  async function completeLogin(data) {
    if (!data?.access_token) {
      throw new Error("La connexion a réussi, mais le token est absent.");
    }

    localStorage.setItem("access_token", data.access_token);
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    setAccessToken(data.access_token);
    cleanupMfaSession();

    await refreshMe({ skipAuthRedirect: true });

    // Always land on /accueil after login; ignore server-side redirect_to
    return "/accueil";
  }

  async function logout() {
    try {
      await stopEltWatchBestEffort();
      await api.post("/auth/logout");
    } catch {
      // ignore
    } finally {
      logoutLocal();
      navigateOnce("/login");
    }
  }

  useEffect(() => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    refreshMe({ skipAuthRedirect: true }).catch((err) => {
      if (err?.response?.status === 401) {
        logoutLocal();
        if (!isAuthFlowPath()) {
          navigateOnce("/login?reason=auth_required");
        }
      }
    });
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return undefined;
    clearAccountStatusTimer();
    accountStatusTimerRef.current = window.setInterval(() => {
      refreshMe({ skipAuthRedirect: true, silent: true }).catch((err) => {
        const detail = err?.response?.data?.detail;
        const detailStatus =
          detail && typeof detail === "object" ? String(detail.status || "") : "";
        const accountStatuses = new Set([
          "account_disabled",
          "account_blocked",
          "account_pending_first_login",
          "account_deleted",
          "account_unavailable",
        ]);

        if (err?.response?.status === 403 && accountStatuses.has(detailStatus)) {
          logoutLocal();
          const message = encodeURIComponent(detail.message || "Compte indisponible.");
          navigateOnce(`/account-disabled?reason=${encodeURIComponent(detailStatus)}&message=${message}`);
        }
      });
    }, ACCOUNT_STATUS_CHECK_MS);
    return () => clearAccountStatusTimer();
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return undefined;

    const refreshPermissions = (event) => {
      const changedDepartment = event?.detail?.departement_nom;
      if (changedDepartment && changedDepartment !== user?.departement_nom && user?.role !== "SUPER_ADMIN") {
        return;
      }
      refreshMe({ skipAuthRedirect: true, silent: true }).catch(() => {});
    };
    const refreshPermissionsFromStorage = (event) => {
      if (event.key === PERMISSIONS_CHANGED_KEY) refreshPermissions();
    };
    const refreshPermissionsOnFocus = () => refreshPermissions();

    window.addEventListener("permissions:changed", refreshPermissions);
    window.addEventListener("permissions:stale", refreshPermissions);
    window.addEventListener("storage", refreshPermissionsFromStorage);
    window.addEventListener("focus", refreshPermissionsOnFocus);
    return () => {
      window.removeEventListener("permissions:changed", refreshPermissions);
      window.removeEventListener("permissions:stale", refreshPermissions);
      window.removeEventListener("storage", refreshPermissionsFromStorage);
      window.removeEventListener("focus", refreshPermissionsOnFocus);
    };
  }, [accessToken, user?.departement_nom, user?.role]);

  useEffect(() => {
    redirectingRef.current = false;
  }, [location.pathname]);

  useEffect(() => {
    function handleAuthRedirect(event) {
      logoutLocal();
      const target = event.detail?.to;
      if (target && !isAuthFlowPath(location.pathname)) {
        navigateOnce(target);
      }
    }

    window.addEventListener("auth:redirect", handleAuthRedirect);
    return () => window.removeEventListener("auth:redirect", handleAuthRedirect);
  }, [location.pathname]);

  useEffect(() => {
    if (!accessToken) return undefined;
    window.addEventListener("pagehide", stopEltWatchOnUnload);
    window.addEventListener("beforeunload", stopEltWatchOnUnload);
    return () => {
      window.removeEventListener("pagehide", stopEltWatchOnUnload);
      window.removeEventListener("beforeunload", stopEltWatchOnUnload);
    };
  }, [accessToken]);

  const value = useMemo(
    () => ({
      accessToken,
      user,
      loading,
      isAuthenticated,
      isAdmin,
      hasRight,
      saveLogin,
      refreshMe,
      completeLogin,
      cleanupMfaSession,
      dashboardForRole,
      logout,
      logoutLocal,
    }),
    [accessToken, user, loading, isAuthenticated, isAdmin]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth doit être utilisé dans AuthProvider");
  }

  return context;
}

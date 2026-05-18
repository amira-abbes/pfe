import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/api";

const AuthContext = createContext(null);
const SESSION_EXPIRED_REASON = "session_expired";
const INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000;
const ACTIVITY_THROTTLE_MS = 1500;
const ACCOUNT_STATUS_CHECK_MS = 30 * 1000;
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

const MFA_SESSION_KEYS = [
  "mfa_token",
  "mfa_email",
  "mfa_role",
  "mfa_setup_token",
];

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
  // Still available for explicit navigation to role-based dashboards
  const normalizedRole = String(role || "USER").toUpperCase();
  if (normalizedRole === "SUPER_ADMIN") return "/super-admin/dashboard";
  if (normalizedRole === "ADMIN") return "/admin/dashboard";
  return "/user/dashboard";
}

function cleanupMfaSession() {
  MFA_SESSION_KEYS.forEach((key) => sessionStorage.removeItem(key));
}

function markActivity() {
  localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
}

function readLastActivityAt() {
  const value = Number(localStorage.getItem(LAST_ACTIVITY_KEY));
  return Number.isFinite(value) && value > 0 ? value : Date.now();
}

function userHasRight(user, code) {
  if (!code) return true;
  if (String(user?.role || "").toUpperCase() === "SUPER_ADMIN") return true;
  return Array.isArray(user?.permissions) && user.permissions.includes(code);
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
  const inactivityTimerRef = useRef(null);
  const accountStatusTimerRef = useRef(null);
  const lastActivityResetRef = useRef(0);
  const redirectingRef = useRef(false);
  const sessionExpiredByInactivityRef = useRef(false);
  const [accessToken, setAccessToken] = useState(() =>
    localStorage.getItem("access_token")
  );
  const [user, setUser] = useState(() => readStoredUser());
  const [loading, setLoading] = useState(() => {
    const token = localStorage.getItem("access_token");
    return Boolean(token);
  });

  const isAuthenticated = Boolean(accessToken);
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  const hasRight = (code) => userHasRight(user, code);

  function clearInactivityTimer() {
    window.clearTimeout(inactivityTimerRef.current);
    inactivityTimerRef.current = null;
  }

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
    markActivity();
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
    setAccessToken(token);
  }

  function logoutLocal() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    localStorage.removeItem(LAST_ACTIVITY_KEY);
    delete api.defaults.headers.common.Authorization;
    clearInactivityTimer();
    clearAccountStatusTimer();
    setAccessToken(null);
    setUser(null);
    setLoading(false);
  }

  async function expireSessionDueToInactivity() {
    sessionExpiredByInactivityRef.current = true;
    try {
      await stopEltWatchBestEffort();
    } finally {
      logoutLocal();
      if (!isAuthFlowPath()) {
        navigateOnce(`/login?reason=${SESSION_EXPIRED_REASON}`);
      }
    }
  }

  function resetInactivityTimer() {
    if (!accessToken) return;
    clearInactivityTimer();
    const elapsed = Date.now() - readLastActivityAt();
    const remaining = Math.max(0, INACTIVITY_TIMEOUT_MS - elapsed);

    // The frontend session expires only after 30 minutes without real user activity.
    inactivityTimerRef.current = window.setTimeout(() => {
      const inactiveFor = Date.now() - readLastActivityAt();
      if (inactiveFor >= INACTIVITY_TIMEOUT_MS) {
        expireSessionDueToInactivity();
        return;
      }
      resetInactivityTimer();
    }, remaining);
  }

  // Any real interaction in the active tab refreshes the shared lastActivity timestamp.
  function handleUserActivity() {
    if (!localStorage.getItem("access_token")) return;
    const now = Date.now();
    if (now - lastActivityResetRef.current < ACTIVITY_THROTTLE_MS) return;
    lastActivityResetRef.current = now;
    markActivity();
    resetInactivityTimer();
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
    sessionExpiredByInactivityRef.current = false;
    if (!data?.access_token) {
      throw new Error("La connexion a réussi, mais le token est absent.");
    }

    localStorage.setItem("access_token", data.access_token);
    markActivity();
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    setAccessToken(data.access_token);

    const currentUser = await refreshMe({ skipAuthRedirect: true });

    // Always land on /accueil after login; ignore server-side redirect_to
    return "/accueil";
  }

  async function logout() {
    sessionExpiredByInactivityRef.current = false;
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
    if (!accessToken) {
      clearInactivityTimer();
      return undefined;
    }

    if (!localStorage.getItem(LAST_ACTIVITY_KEY)) {
      markActivity();
    }
    resetInactivityTimer();

    const events = [
      "mousemove",
      "mousedown",
      "click",
      "keydown",
      "scroll",
      "touchstart",
    ];

    events.forEach((eventName) => {
      window.addEventListener(eventName, handleUserActivity, eventName === "scroll" ? { capture: true, passive: true } : { passive: true });
    });

    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      const inactiveFor = Date.now() - readLastActivityAt();
      if (inactiveFor >= INACTIVITY_TIMEOUT_MS) {
        expireSessionDueToInactivity();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInactivityTimer();
      // Cleanup prevents duplicated listeners/timers after navigation or refresh.
      events.forEach((eventName) => {
        window.removeEventListener(eventName, handleUserActivity, eventName === "scroll" ? { capture: true } : undefined);
      });
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
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
    redirectingRef.current = false;
  }, [location.pathname]);

  useEffect(() => {
    function handleAuthRedirect(event) {
      sessionExpiredByInactivityRef.current = false;
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

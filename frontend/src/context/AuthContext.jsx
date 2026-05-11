import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/api";

const AuthContext = createContext(null);
const INACTIVITY_LIMIT_MS = 15 * 60 * 1000;
const ACTIVITY_THROTTLE_MS = 1500;
const ACCOUNT_STATUS_CHECK_MS = 30 * 1000;
const LAST_ACTIVITY_KEY = "lastActivityAt";

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
  const inactivityTimerRef = useRef(null);
  const accountStatusTimerRef = useRef(null);
  const lastActivityResetRef = useRef(0);
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
    window.clearInterval(accountStatusTimerRef.current);
    accountStatusTimerRef.current = null;
    setAccessToken(null);
    setUser(null);
    setLoading(false);
  }

  async function expireSessionDueToInactivity() {
    try {
      await stopEltWatchBestEffort();
    } finally {
      logoutLocal();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.replace("/login?reason=session_expired");
      }
    }
  }

  function resetInactivityTimer() {
    if (!accessToken) return;
    clearInactivityTimer();
    const elapsed = Date.now() - readLastActivityAt();
    const remaining = Math.max(0, INACTIVITY_LIMIT_MS - elapsed);

    inactivityTimerRef.current = window.setTimeout(() => {
      const inactiveFor = Date.now() - readLastActivityAt();
      if (inactiveFor >= INACTIVITY_LIMIT_MS) {
        expireSessionDueToInactivity();
        return;
      }
      resetInactivityTimer();
    }, remaining);
  }

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
    setLoading(true);

    try {
      const response = await api.get("/auth/me", {
        skipAuthRedirect: options.skipAuthRedirect === true,
      });
      setUser(response.data);
      localStorage.setItem("current_user", JSON.stringify(response.data));
      return response.data;
    } finally {
      setLoading(false);
    }
  }

  async function completeLogin(data) {
    if (!data?.access_token) {
      throw new Error("La connexion a réussi, mais le token est absent.");
    }

    localStorage.setItem("access_token", data.access_token);
    markActivity();
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    setAccessToken(data.access_token);

    const currentUser = await refreshMe({ skipAuthRedirect: true });

    return data.redirect_to || dashboardForRole(data.role || currentUser?.role);
  }

  async function logout() {
    try {
      await stopEltWatchBestEffort();
      await api.post("/auth/logout");
    } catch {
      // ignore
    } finally {
      logoutLocal();
      window.location.href = "/login";
    }
  }

  useEffect(() => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    refreshMe({ skipAuthRedirect: true }).catch(() => logoutLocal());
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      clearInactivityTimer();
      return undefined;
    }

    markActivity();
    resetInactivityTimer();

    const events = [
      "mousemove",
      "mousedown",
      "click",
      "keydown",
      "scroll",
      "touchstart",
      "touchmove",
      "focus",
    ];

    events.forEach((eventName) => {
      window.addEventListener(eventName, handleUserActivity, eventName === "scroll" ? { capture: true, passive: true } : { passive: true });
    });

    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      const inactiveFor = Date.now() - readLastActivityAt();
      if (inactiveFor >= INACTIVITY_LIMIT_MS) {
        expireSessionDueToInactivity();
        return;
      }
      handleUserActivity();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInactivityTimer();
      events.forEach((eventName) => {
        window.removeEventListener(eventName, handleUserActivity, eventName === "scroll" ? { capture: true } : undefined);
      });
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return undefined;
    accountStatusTimerRef.current = window.setInterval(() => {
      refreshMe().catch(() => {});
    }, ACCOUNT_STATUS_CHECK_MS);
    return () => window.clearInterval(accountStatusTimerRef.current);
  }, [accessToken]);

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

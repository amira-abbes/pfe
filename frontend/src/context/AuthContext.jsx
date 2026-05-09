import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../api/api";

const AuthContext = createContext(null);

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

function userHasRight(user, code) {
  if (!code) return true;
  if (String(user?.role || "").toUpperCase() === "SUPER_ADMIN") return true;
  return Array.isArray(user?.permissions) && user.permissions.includes(code);
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessToken] = useState(() =>
    localStorage.getItem("access_token")
  );
  const [user, setUser] = useState(() => readStoredUser());
  const [loading, setLoading] = useState(() => {
    const token = localStorage.getItem("access_token");
    return Boolean(token && !readStoredUser());
  });

  const isAuthenticated = Boolean(accessToken);
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user?.role);
  const hasRight = (code) => userHasRight(user, code);

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
    setAccessToken(null);
    setUser(null);
    setLoading(false);
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
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    setAccessToken(data.access_token);

    const currentUser = await refreshMe({ skipAuthRedirect: true });

    // Always land on /accueil after login; ignore server-side redirect_to
    return "/accueil";
  }

  async function logout() {
    try {
      await api.post("/auth/logout");
    } catch {
      // ignore
    } finally {
      logoutLocal();
      window.location.href = "/login";
    }
  }

  useEffect(() => {
    if (accessToken && !user) {
      refreshMe().catch(() => logoutLocal());
    }
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

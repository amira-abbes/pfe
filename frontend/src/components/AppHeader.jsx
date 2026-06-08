import { LogOut, UserRound } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const ROLE_LABELS = {
  SUPER_ADMIN: "Super Administrateur Plateforme",
  ADMIN: "Administrateur Départemental",
  USER: "Employé Départemental",
};

const ROLE_BADGES = {
  SUPER_ADMIN: "S.ADMIN",
  ADMIN: "ADMIN",
  USER: "USER",
};

function humanizeRole(role) {
  if (!role) return "Utilisateur";

  return role
    .toString()
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function buildUserSummary(user) {
  const roleLabel = ROLE_LABELS[user?.role] || humanizeRole(user?.role);
  const identity = user?.nom_complet || user?.email || user?.login;
  const department = user?.departement_nom || user?.departement;
  const normalizedIdentity = String(identity || "").trim().toLowerCase();
  const normalizedRoleLabel = String(roleLabel || "").trim().toLowerCase();
  const visibleIdentity = normalizedIdentity && normalizedIdentity !== normalizedRoleLabel ? identity : null;

  return [roleLabel, visibleIdentity, department].filter(Boolean).join(" · ");
}

export default function AppHeader() {
  const { user, logout } = useAuth();
  const userSummary = buildUserSummary(user);
  const roleBadge = ROLE_BADGES[user?.role] || user?.role || "USER";

  return (
    <header className="top-header">
      <div className="top-header-brand">
        <img src="/tt-logo.png" alt="Tunisie Telecom" />
        <div className="top-header-text">
          <span className="top-header-title">Tunisie Telecom</span>
          <span className="top-header-sub">Plateforme Interne</span>
        </div>
      </div>

      <div className="top-header-right">
        <div className="user-chip" title={userSummary}>
          <span className="user-chip-avatar" aria-hidden="true">
            <UserRound size={16} />
            <i />
          </span>
          <span className="user-chip-content">
            <span className="user-chip-label">{userSummary}</span>
            <span className="user-chip-role">{roleBadge}</span>
          </span>
        </div>
        <button className="logout-chip" onClick={logout} title="Déconnexion" aria-label="Déconnexion">
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}

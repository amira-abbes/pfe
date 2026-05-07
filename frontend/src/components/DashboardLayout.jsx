import {
  BarChart3,
  Building2,
  LayoutDashboard,
  LogOut,
  Menu,
  PlayCircle,
  TrendingDown,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function DashboardLayout({ children }) {
  const { hasRight, user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = user?.role === "ADMIN";
  const canManageDepartments = hasRight("gerer_departements") || hasRight("gerer_roles");

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="dashboard-shell">
      <header className="dashboard-navbar">
        <div className="dashboard-brand">
          <img src="/tt-logo.png" alt="Tunisie Telecom" />
          <span>TT Platform</span>
        </div>

        <button
          type="button"
          className="dashboard-menu-button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>

        <nav className={`dashboard-nav ${menuOpen ? "is-open" : ""}`}>
          <NavLink to={isSuperAdmin ? "/super-admin/dashboard" : isAdmin ? "/admin/dashboard" : "/user/dashboard"} onClick={closeMenu}>
            <LayoutDashboard size={17} />
            Accueil
          </NavLink>
          {hasRight("dashboard_service_sos") && (
            <NavLink to="/dashboard/service-sos" onClick={closeMenu}>
              <BarChart3 size={17} />
              Dashboard Service SOS
            </NavLink>
          )}
          {hasRight("lancer_elt") && (
            <NavLink to="/admin/elt" onClick={closeMenu}>
              <PlayCircle size={17} />
              Traitement ELT
            </NavLink>
          )}
          {hasRight("dashboard_parc_service_sos") && (
            <NavLink to="/dashboard/parc-service-sos" onClick={closeMenu}>
              <BarChart3 size={17} />
              Dashboard Parc Service SOS
            </NavLink>
          )}
          {hasRight("dashboard_bad_debts") && (
            <NavLink to="/dashboard/bad-debts" onClick={closeMenu}>
              <TrendingDown size={17} />
              Dashboard Bad Debts
            </NavLink>
          )}
          {hasRight("gerer_utilisateurs") && (
            <NavLink to="/admin/users" onClick={closeMenu}>
              <Users size={17} />
              Utilisateurs
            </NavLink>
          )}
          {canManageDepartments && (
            <NavLink to="/admin/departements" onClick={closeMenu}>
              <Building2 size={17} />
              Départements & permissions
            </NavLink>
          )}
        </nav>

        <div className="dashboard-user">
          <span>{user?.nom_complet || user?.email || "Utilisateur"}</span>
          <button type="button" onClick={logout} aria-label="Déconnexion">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="dashboard-main">{children}</main>
    </div>
  );
}

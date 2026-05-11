import {
  BarChart3,
  Building2,
  KeyRound,
  LayoutDashboard,
  LogOut,
  PlayCircle,
  ShieldCheck,
  TrendingDown,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function Layout({ children, title, subtitle, hideSidebar = false, className = "" }) {
  const { hasRight, user, logout } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = user?.role === "ADMIN";
  const isAdminArea = isAdmin || isSuperAdmin;
  const isEltLayout = className.includes("app-shell--elt");

  return (
    <div className={`app-shell ${hideSidebar ? "app-shell--no-sidebar" : ""} ${className}`}>
      {!hideSidebar && (
      <aside className="sidebar">
        <div className="brand">
          <img src="/tt-logo.png" alt="Tunisie Telecom" />
          <div>
            <h2>TT Platform</h2>
            <p>Plateforme interne</p>
          </div>
        </div>

        <nav className="nav">
          {isAdminArea ? (
            <>
              <NavLink to={isSuperAdmin ? "/super-admin/dashboard" : "/admin/dashboard"}>
                <LayoutDashboard size={18} />
                Dashboard
              </NavLink>
              <NavLink to="/security">
                <KeyRound size={18} />
                Sécurité
              </NavLink>
              {hasRight("gerer_utilisateurs") && (
                <NavLink to="/admin/users">
                  <Users size={18} />
                  Utilisateurs
                </NavLink>
              )}
              {(hasRight("gerer_departements") || hasRight("gerer_roles")) && (
                <NavLink to="/admin/departements">
                  <Building2 size={18} />
                  Départements & permissions
                </NavLink>
              )}
              {hasRight("dashboard_service_sos") && (
                <NavLink to="/dashboard/service-sos">
                  <BarChart3 size={18} />
                  Dashboard Service SOS
                </NavLink>
              )}
              {hasRight("lancer_elt") && (
                <NavLink to="/admin/elt">
                  <PlayCircle size={18} />
                  Traitement ELT
                </NavLink>
              )}
              {hasRight("dashboard_parc_service_sos") && (
                <NavLink to="/dashboard/parc-service-sos">
                  <BarChart3 size={18} />
                  Dashboard Parc Service SOS
                </NavLink>
              )}
              {hasRight("dashboard_bad_debts") && (
                <NavLink to="/dashboard/bad-debts">
                  <TrendingDown size={18} />
                  Dashboard Bad Debts
                </NavLink>
              )}
            </>
          ) : (
            <>
              <NavLink to="/dashboard">
                <LayoutDashboard size={18} />
                Dashboard
              </NavLink>
              {hasRight("dashboard_service_sos") && (
                <NavLink to="/dashboard/service-sos">
                  <BarChart3 size={18} />
                  Dashboard Service SOS
                </NavLink>
              )}
              {hasRight("dashboard_parc_service_sos") && (
                <NavLink to="/dashboard/parc-service-sos">
                  <BarChart3 size={18} />
                  Dashboard Parc Service SOS
                </NavLink>
              )}
              {hasRight("dashboard_bad_debts") && (
                <NavLink to="/dashboard/bad-debts">
                  <TrendingDown size={18} />
                  Dashboard Bad Debts
                </NavLink>
              )}
            </>
          )}
        </nav>

        <div className="sidebar-user">
          <div className="user-pill">
            <ShieldCheck size={18} />
            <div>
              <strong>{user?.nom_complet || "Utilisateur"}</strong>
              <span>{user?.role || "USER"}</span>
            </div>
          </div>

          <button className="logout-btn" onClick={logout}>
            <LogOut size={18} />
            Déconnexion
          </button>
        </div>
      </aside>
      )}

      <main className="main-content">
        {!isEltLayout && (
          <header className="topbar">
            <div>
              <h1>{title}</h1>
              {subtitle && <p>{subtitle}</p>}
            </div>
          </header>
        )}

        {children}
      </main>
    </div>
  );
}

import {
  Building2,
  KeyRound,
  LayoutDashboard,
  LogOut,
  PlayCircle,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout({ children, title, subtitle }) {
  const { user, logout } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = user?.role === "ADMIN";
  const isAdminArea = isAdmin || isSuperAdmin;

  return (
    <div className="app-shell">
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
              <NavLink to="/admin/users">
                <Users size={18} />
                Utilisateurs
              </NavLink>
              {isSuperAdmin && (
                <NavLink to="/admin/departements">
                  <Building2 size={18} />
                  Départements & permissions
                </NavLink>
              )}
              <NavLink to="/admin/elt">
                <PlayCircle size={18} />
                Traitement ELT
              </NavLink>
            </>
          ) : (
            <NavLink to="/dashboard">
              <LayoutDashboard size={18} />
              Dashboard
            </NavLink>
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

      <main className="main-content">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </div>

          {isAdminArea && !user?.webauthn_admin_active && (
            <div className="warning-pill">
              <UserCog size={18} />
              WebAuthn non configuré pour actions sensibles
            </div>
          )}
        </header>

        {children}
      </main>
    </div>
  );
}

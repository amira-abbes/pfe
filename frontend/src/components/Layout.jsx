import {
  BarChart3,
  Building2,
  Home,
  KeyRound,
  LayoutDashboard,
  LogOut,
  PlayCircle,
  TrendingDown,
  User,
  Users,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout({ children, title, subtitle, noPadding = false, noScroll = false }) {
  const { user, logout, hasRight } = useAuth();
  const location = useLocation();
  const currentPath = location.pathname;

  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = user?.role === "ADMIN";

  // Navigation Items
  const navItems = [
    {
      to: isSuperAdmin ? "/super-admin/dashboard" : isAdmin ? "/admin/dashboard" : "/dashboard",
      icon: (isAdmin || isSuperAdmin) ? <LayoutDashboard size={22} /> : <User size={22} />,
      label: (isAdmin || isSuperAdmin) ? "Dashboard" : "Mon Compte",
      id: "dashboard"
    },
    {
      to: "/security",
      icon: <KeyRound size={22} />,
      label: "Sécurité",
      id: "security"
    },
    {
      to: "/admin/users",
      icon: <Users size={22} />,
      label: "Utilisateurs",
      id: "users",
      hidden: !hasRight("gerer_utilisateurs")
    },
    {
      to: "/admin/departements",
      icon: <Building2 size={22} />,
      label: "Départements & permissions",
      id: "depts",
      hidden: !(hasRight("gerer_departements") || hasRight("gerer_roles"))
    },
    {
      to: "/dashboard/service-sos",
      icon: <BarChart3 size={22} />,
      label: "Dashboard Service SOS",
      id: "service-sos",
      hidden: !hasRight("dashboard_service_sos")
    },
    {
      to: "/admin/elt",
      icon: <PlayCircle size={22} />,
      label: "Traitement ELT",
      id: "elt",
      hidden: !hasRight("lancer_elt")
    },
    {
      to: "/dashboard/parc-service-sos",
      icon: <BarChart3 size={22} />,
      label: "Dashboard Parc Service SOS",
      id: "parc-service-sos",
      hidden: !hasRight("dashboard_parc_service_sos")
    },
    {
      to: "/dashboard/bad-debts",
      icon: <TrendingDown size={22} />,
      label: "Dashboard Bad Debts",
      id: "bad-debts",
      hidden: !hasRight("dashboard_bad_debts")
    },
    {
      to: "/accueil",
      icon: <Home size={22} />,
      label: "Accueil",
      id: "accueil"
    },
  ];

  return (
    <div className={`app-shell-bottom ${noScroll ? "no-scroll" : ""}`}>
      {/* ── Top Header ── */}
      <header className="top-header">
        <div className="top-header-brand">
          <img src="/tt-logo.png" alt="Tunisie Telecom" />
          <div className="top-header-text">
            <span className="top-header-title">Tunisie Telecom</span>
            <span className="top-header-sub">Plateforme Interne</span>
          </div>
        </div>

        <div className="top-header-right">
          <div className="user-chip">
            <span>{user?.nom_complet || "Utilisateur"}</span>
            <span className="user-chip-role">{user?.role === "SUPER_ADMIN" ? "S.Admin" : user?.role}</span>
          </div>
          <button className="logout-chip" onClick={logout} title="Déconnexion">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {/* ── Main Content ── */}
      <main className={`bottom-main-content ${noPadding ? "p-0" : ""} ${noScroll ? "no-scroll" : ""}`}>
        {title && !noPadding && (
          <div style={{ marginBottom: "24px" }}>
            <h1 style={{ margin: 0, fontSize: "24px", color: "#0f172a", fontWeight: 800 }}>{title}</h1>
            {subtitle && <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "14px" }}>{subtitle}</p>}
          </div>
        )}
        {children}
      </main>

      {/* ── Bottom Navbar ── */}
      <nav className="bottom-navbar">
        {navItems.filter(item => !item.hidden).map((item) => {
          const isActive = currentPath === item.to || (item.to !== "/accueil" && currentPath.startsWith(item.to));
          return (
            <Link
              key={item.id}
              to={item.to}
              className={`bnav-item ${isActive ? "active" : ""}`}
            >
              <div className="bnav-bubble">
                {item.icon}
              </div>
              <span className="bnav-label">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

import {
  BarChart3,
  Building2,
  Home,
  KeyRound,
  PlayCircle,
  TrendingDown,
  UserRound,
  Users,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AppHeader from "./AppHeader";

export default function Layout({ children, title, subtitle, noPadding = false, noScroll = false, className = "" }) {
  const { user, hasRight } = useAuth();
  const location = useLocation();
  const currentPath = location.pathname;

  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = ["ADMIN", "ADMIN_DEPARTEMENTAL"].includes(user?.role);
  const isEltLayout = className.includes("app-shell--elt");

  const navItems = [
    {
      to: "/accueil",
      icon: <Home size={22} />,
      label: "Accueil",
      id: "accueil",
    },
    {
      to: "/mon-compte",
      icon: <UserRound size={22} />,
      label: "Mon compte",
      id: "mon-compte",
    },
    {
      to: "/admin/users",
      icon: <Users size={22} />,
      label: "Utilisateurs",
      id: "users",
      hidden: !isSuperAdmin,
    },
    {
      to: "/admin/departements",
      icon: <Building2 size={22} />,
      label: "Départements & permissions",
      id: "depts",
      hidden: !isSuperAdmin,
    },
    {
      to: "/dashboard/service-sos",
      icon: <BarChart3 size={22} />,
      label: "Dashboard Service SOS",
      id: "service-sos",
      hidden: !hasRight("dashboard_service_sos"),
    },
    {
      to: "/dashboard/parc-service-sos",
      icon: <BarChart3 size={22} />,
      label: "Dashboard Parc Service SOS",
      id: "parc-service-sos",
      hidden: !hasRight("dashboard_parc_service_sos"),
    },
    {
      to: "/dashboard/bad-debts",
      icon: <TrendingDown size={22} />,
      label: "Dashboard Bad Debts",
      id: "bad-debts",
      hidden: !hasRight("dashboard_bad_debts"),
    },
    {
      to: "/admin/elt",
      icon: <PlayCircle size={22} />,
      label: "Traitement ELT",
      id: "elt",
      hidden: !hasRight("lancer_elt"),
    },
    {
      to: "/admin/mon-departement",
      icon: <Building2 size={22} />,
      label: "Mon département",
      id: "my-department",
      hidden: !isAdmin,
    },
    {
      to: "/security",
      icon: <KeyRound size={22} />,
      label: "Sécurité",
      id: "security",
    },
  ];

  return (
    <div className={`app-shell-bottom ${noScroll ? "no-scroll" : ""} ${className}`}>
      <AppHeader />

      <main className={`bottom-main-content ${noPadding ? "p-0" : ""} ${noScroll ? "no-scroll" : ""}`}>
        {title && !noPadding && !isEltLayout && (
          <div style={{ marginBottom: "24px" }}>
            <h1 style={{ margin: 0, fontSize: "24px", color: "#0f172a", fontWeight: 800 }}>{title}</h1>
            {subtitle && <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "14px" }}>{subtitle}</p>}
          </div>
        )}
        {children}
      </main>

      <nav className="bottom-navbar">
        {navItems.filter((item) => !item.hidden).map((item) => {
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

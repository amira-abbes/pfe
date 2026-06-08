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
import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AppHeader from "./AppHeader";
import PageHeader from "./PageHeader";

export default function Layout({ children, eyebrow, title, subtitle, action, noPadding = false, noScroll = false, className = "" }) {
  const ambientRef = useRef(null);
  const { user, hasRight } = useAuth();
  const location = useLocation();
  const currentPath = location.pathname;

  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = ["ADMIN", "ADMIN_DEPARTEMENTAL"].includes(user?.role);

  useEffect(() => {
    const ambient = ambientRef.current;
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!ambient || !finePointer.matches || reducedMotion.matches) return undefined;

    let frameId = 0;
    const handlePointerMove = (event) => {
      if (frameId) cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(() => {
        const x = (event.clientX / window.innerWidth - 0.5) * 2;
        const y = (event.clientY / window.innerHeight - 0.5) * 2;
        ambient.style.setProperty("--parallax-x", `${x * 16}px`);
        ambient.style.setProperty("--parallax-y", `${y * 12}px`);
        ambient.style.setProperty("--parallax-x-soft", `${x * -9}px`);
        ambient.style.setProperty("--parallax-y-soft", `${y * -7}px`);
      });
    };

    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      if (frameId) cancelAnimationFrame(frameId);
    };
  }, []);

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
      <div ref={ambientRef} className="platform-ambient" aria-hidden="true">
        <span className="platform-aurora platform-aurora-one" />
        <span className="platform-aurora platform-aurora-two" />
        <span className="platform-mesh" />
        <span className="platform-glow platform-glow-blue" />
        <span className="platform-glow platform-glow-violet" />
        <span className="platform-glow platform-glow-cyan" />
        <span className="platform-dust platform-dust-one" />
        <span className="platform-dust platform-dust-two" />
      </div>
      <AppHeader />

      <main className={`bottom-main-content ${noPadding ? "p-0" : ""} ${noScroll ? "no-scroll" : ""}`}>
        {title && !noPadding && <PageHeader eyebrow={eyebrow} title={title} subtitle={subtitle} action={action} />}
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

import {
  ArrowRight,
  BarChart2,
  Brain,
  Building2,
  Database,
  LayoutDashboard,
  PieChart,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  Users,
} from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

function useScrollReveal() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("reveal-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    const elements = document.querySelectorAll(".reveal-hidden");
    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);
}

export default function AccueilPage() {
  const { user, hasRight } = useAuth();
  useScrollReveal();

  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = user?.role === "ADMIN";
  const isAdminArea = isAdmin || isSuperAdmin;

  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Bonjour" : hour < 18 ? "Bon après-midi" : "Bonsoir";

  const allCards = [
    {
      to: "/dashboard/parc-service-sos",
      icon: <BarChart2 size={40} />,
      label: "Tableau de bord du Parc d'abonnés",
      desc: "Vue d'ensemble et évolution du parc d'abonnés Tunisie Telecom entre abonné prepaid et hybride , et data et solde",
      color: "#3b82f6", // blue
      hidden: !hasRight("dashboard_parc_service_sos"),
    },
    {
      to: "/dashboard/service-sos",
      icon: <PieChart size={40} />,
      label: "Tableau de Bord de visualisation des services SOS Solde et Data de Tunisie Télécom",
      desc: "Tableau de bord de visualisation des services SOS Solde et Data",
      color: "#8b5cf6", // purple
      badge: "PowerBI",
      badgeColor: "badge-orange",
      hidden: !hasRight("dashboard_service_sos"),
    },
    {
      to: "/dashboard/bad-debts",
      icon: <Brain size={40} />,
      label: "Bad Debts Dashboard",
      desc: "Analyse prédictive des mauvaises créances générée par Machine Learning",
      color: "#ef4444", // red/coral
      badge: "ML",
      badgeColor: "badge-green",
      hidden: !hasRight("dashboard_bad_debts"),
    },
    {
      to: "/admin/users",
      icon: <Users size={40} />,
      label: "Utilisateurs",
      desc: "Créer, modifier et gérer les comptes utilisateurs et leurs accès",
      color: "#6366f1", // indigo
      hidden: !hasRight("gerer_utilisateurs"),
    },
    {
      to: "/admin/departements",
      icon: <Building2 size={40} />,
      label: "Départements",
      desc: "Configurer les départements et les permissions d'accès",
      color: "#f97316", // orange
      hidden: !(hasRight("gerer_departements") || hasRight("gerer_roles")),
    },
  ];

  const cards = allCards.filter(c => !c.hidden);

  return (
    <Layout title="Accueil" subtitle="Plateforme interne Tunisie Telecom">

      {/* ── Ambient Aurora background mesh ── */}
      <div className="accueil-bg" aria-hidden="true">
        <div className="accueil-mesh" />
      </div>

      {/* ── Hero welcome banner ── */}
      <div className="accueil-hero">

        {/* Decorative blur circles */}
        <div className="accueil-hero-blur-tr" aria-hidden="true" />
        <div className="accueil-hero-blur-bl" aria-hidden="true" />

        {/* LEFT COLUMN — Text */}
        <div className="accueil-hero-left">
          {/* Badge pill */}
          <div className="accueil-greeting">
            <Sparkles size={16} className="accueil-sparkle" />
            {greeting}, {user?.nom_complet?.split(" ")[0] || "Utilisateur"} !
          </div>

          {/* Title */}
          <h1 className="accueil-title">
            Bienvenue sur la plateforme
            <span className="accueil-title-brand">Tunisie Telecom</span>
          </h1>

          {/* Subtitle */}
          <p className="accueil-subtitle">
            {isAdminArea
              ? "Gérez vos équipes, sécurisez les accès et pilotez les traitements depuis un seul espace."
              : "Accédez à votre espace personnel, gérez votre sécurité et consultez vos informations."}
          </p>

          {/* CTA Button */}
          <Link to="/dashboard/parc-service-sos" className="accueil-cta-btn">
            Commencer →
          </Link>

          {/* Role badge */}
          <div>
            <div className="accueil-role-badge">
              <ShieldCheck size={14} />
              {user?.role === "SUPER_ADMIN"
                ? "Super Administrateur"
                : user?.role === "ADMIN"
                  ? "Administrateur"
                  : "Utilisateur"}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN — Floating device mockups */}
        <div className="accueil-hero-right" aria-hidden="true">
          {/* Tablet Mockup */}
          <div className="hero-mockup-tablet">
            {/* Mini nav bar */}
            <div className="hero-mockup-tablet-nav">
              <div className="hero-mock-nav-dot" style={{background: '#ef4444'}} />
              <div className="hero-mock-nav-dot" style={{background: '#f59e0b'}} />
              <div className="hero-mock-nav-dot" style={{background: '#10b981'}} />
              <div className="hero-mock-nav-bar" />
            </div>
            {/* Bar chart SVG */}
            <div className="hero-mockup-tablet-body">
              <svg width="100%" height="130" viewBox="0 0 268 130" xmlns="http://www.w3.org/2000/svg">
                {/* Y-axis gridlines */}
                <line x1="0" y1="110" x2="268" y2="110" stroke="#e2e8f0" strokeWidth="1"/>
                <line x1="0" y1="80"  x2="268" y2="80"  stroke="#e2e8f0" strokeWidth="1" strokeDasharray="4,4"/>
                <line x1="0" y1="50"  x2="268" y2="50"  stroke="#e2e8f0" strokeWidth="1" strokeDasharray="4,4"/>
                <line x1="0" y1="20"  x2="268" y2="20"  stroke="#e2e8f0" strokeWidth="1" strokeDasharray="4,4"/>
                {/* Bars */}
                <rect x="16"  y="50" width="34" height="60" rx="5" fill="#3b82f6"/>
                <rect x="64"  y="30" width="34" height="80" rx="5" fill="#ef4444"/>
                <rect x="112" y="60" width="34" height="50" rx="5" fill="#10b981"/>
                <rect x="160" y="20" width="34" height="90" rx="5" fill="#8b5cf6"/>
                <rect x="208" y="40" width="34" height="70" rx="5" fill="#f59e0b"/>
                {/* Labels */}
                <text x="33"  y="126" textAnchor="middle" fontSize="9" fill="#94a3b8">Jan</text>
                <text x="81"  y="126" textAnchor="middle" fontSize="9" fill="#94a3b8">Fév</text>
                <text x="129" y="126" textAnchor="middle" fontSize="9" fill="#94a3b8">Mar</text>
                <text x="177" y="126" textAnchor="middle" fontSize="9" fill="#94a3b8">Avr</text>
                <text x="225" y="126" textAnchor="middle" fontSize="9" fill="#94a3b8">Mai</text>
              </svg>
            </div>
          </div>

          {/* Phone Mockup */}
          <div className="hero-mockup-mobile">
            <div className="hero-mock-mobile-line wide" />
            <div className="hero-mock-mobile-line medium" />
            <div className="hero-mock-mobile-line narrow" />
            <div style={{height: '1px', background: 'rgba(255,255,255,0.15)', margin: '4px 0'}} />
            <div className="hero-mock-mobile-line wide" />
            <div className="hero-mock-mobile-line medium" />
          </div>
        </div>

      </div>

      {/* ── Section 1: Hero Extension & Mockups ── */}
      <div className="landing-hero-extension reveal-hidden">
        <div className="landing-devices">
          {/* Laptop Mockup */}
          <div className="device-laptop">
            <div className="mock-header">
              <div className="mock-dot red" />
              <div className="mock-dot yellow" />
              <div className="mock-dot green" />
            </div>
            <div className="mock-body">
              <div className="mock-sidebar">
                <div className="mock-side-item" />
                <div className="mock-side-item" />
                <div className="mock-side-item" />
              </div>
              <div className="mock-content">
                <div className="mock-grid">
                  <div className="mock-card"><div className="mock-line" style={{width: '60%'}}/></div>
                  <div className="mock-card"><div className="mock-line" style={{width: '40%'}}/></div>
                  <div className="mock-card"><div className="mock-line" style={{width: '80%'}}/></div>
                </div>
                <div className="mock-chart">
                  <div className="mock-bar" style={{height: '40%'}} />
                  <div className="mock-bar" style={{height: '70%'}} />
                  <div className="mock-bar" style={{height: '50%'}} />
                  <div className="mock-bar" style={{height: '90%'}} />
                  <div className="mock-bar" style={{height: '30%'}} />
                </div>
              </div>
            </div>
          </div>
          
          {/* Phone Mockup */}
          <div className="device-phone">
            <div className="mock-phone-header" />
            <div className="mock-phone-card">
              <div className="mock-phone-circle" />
              <div style={{flex: 1}}>
                <div className="mock-line" style={{width: '80%'}} />
                <div className="mock-line" style={{width: '40%'}} />
              </div>
            </div>
            <div className="mock-phone-card">
              <div className="mock-phone-circle" />
              <div style={{flex: 1}}>
                <div className="mock-line" style={{width: '60%'}} />
                <div className="mock-line" style={{width: '30%'}} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 2: La Solution Complète ── */}
      <div className="landing-section reveal-hidden">
        <h2 className="landing-title-centered">La Solution Complète</h2>
        <div className="landing-features-grid">
          <div className="landing-feature-card">
            <div className="landing-feature-icon" style={{background: '#eff6ff', color: '#3b82f6'}}>
              <BarChart2 size={32} />
            </div>
            <h3>Tableaux de Bord</h3>
            <p>Visualisez vos données en temps réel avec des dashboards interactifs et des rapports Power BI.</p>
          </div>
          <div className="landing-feature-card">
            <div className="landing-feature-icon" style={{background: '#f3e8ff', color: '#9333ea'}}>
              <Users size={32} />
            </div>
            <h3>Gestion des Accès</h3>
            <p>Contrôlez les permissions et les accès par département depuis un seul espace centralisé.</p>
          </div>
          <div className="landing-feature-card">
            <div className="landing-feature-icon" style={{background: '#dcfce7', color: '#16a34a'}}>
              <ShieldCheck size={32} />
            </div>
            <h3>Sécurité Avancée</h3>
            <p>Protégez votre compte avec MFA, WebAuthn et codes de secours pour une sécurité optimale.</p>
          </div>
        </div>
      </div>

      {/* ── Section 3: Anticipez les Mauvaises Créances ── */}
      <div className="landing-section gray reveal-hidden">
        <div className="landing-inner landing-split">
          <div className="landing-text">
            <span className="landing-tag ml">Machine Learning</span>
            <h2 className="landing-title">Anticipez les Mauvaises Créances</h2>
            <p>Notre dashboard Bad Debts utilise des modèles de Machine Learning pour prédire et analyser les risques financiers en temps réel.</p>
            {hasRight("dashboard_bad_debts") && (
              <Link to="/dashboard/bad-debts" className="btn btn-primary" style={{borderRadius: '12px'}}>
                Découvrir →
              </Link>
            )}
          </div>
          <div className="landing-visual">
            <span className="accueil-card-badge badge-green" style={{top: '-12px', right: '-12px', zIndex: 20}}>ML</span>
            <div className="browser-mockup">
              <div className="browser-header">
                <div className="mock-dot red" />
                <div className="mock-dot yellow" />
                <div className="mock-dot green" />
              </div>
              <div className="browser-body">
                <div className="mock-grid">
                  <div className="mock-card"><div className="mock-line" style={{width: '70%'}}/><div className="mock-line" style={{width: '30%'}}/></div>
                  <div className="mock-card"><div className="mock-line" style={{width: '50%'}}/><div className="mock-line" style={{width: '40%'}}/></div>
                  <div className="mock-card"><div className="mock-line" style={{width: '90%'}}/><div className="mock-line" style={{width: '20%'}}/></div>
                </div>
                <div className="mock-chart">
                  <div className="mock-bar" style={{height: '20%', background: '#ef4444'}} />
                  <div className="mock-bar" style={{height: '40%', background: '#f59e0b'}} />
                  <div className="mock-bar" style={{height: '60%', background: '#10b981'}} />
                  <div className="mock-bar" style={{height: '80%', background: '#3b82f6'}} />
                  <div className="mock-bar" style={{height: '50%', background: '#8b5cf6'}} />
                  <div className="mock-bar" style={{height: '90%', background: '#6366f1'}} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 4: Power BI Integration ── */}
      <div className="landing-section reveal-hidden">
        <div className="landing-split reverse">
          <div className="landing-text">
            <span className="landing-tag powerbi">Power BI</span>
            <h2 className="landing-title">Visualisation des Services SOS Solde & Data</h2>
            <p>Accédez aux tableaux de bord Power BI directement intégrés à la plateforme pour suivre les services SOS Solde et Data de Tunisie Télécom.</p>
            {(hasRight("dashboard_service_sos") || hasRight("dashboard_parc_service_sos")) && (
              <Link to="/dashboard/service-sos" className="btn btn-primary" style={{borderRadius: '12px'}}>
                Accéder →
              </Link>
            )}
          </div>
          <div className="landing-visual">
            <span className="accueil-card-badge badge-orange" style={{top: '-12px', right: '-12px', zIndex: 20}}>PowerBI</span>
            <div className="browser-mockup">
              <div className="browser-header">
                <div className="mock-dot red" />
                <div className="mock-dot yellow" />
                <div className="mock-dot green" />
              </div>
              <div className="browser-body" style={{flexDirection: 'row', gap: '24px'}}>
                <div style={{flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                  <div style={{width: '120px', height: '120px', borderRadius: '50%', background: 'conic-gradient(#8b5cf6 0% 40%, #c084fc 40% 75%, #e9d5ff 75% 100%)'}} />
                </div>
                <div style={{flex: 1, display: 'flex', flexDirection: 'column', gap: '12px', justifyContent: 'center'}}>
                  <div className="mock-card"><div className="mock-line" style={{width: '80%'}}/></div>
                  <div className="mock-card"><div className="mock-line" style={{width: '60%'}}/></div>
                  <div className="mock-card"><div className="mock-line" style={{width: '90%'}}/></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 5: Accès Rapide ── */}
      <div className="landing-section reveal-hidden" style={{paddingTop: '24px'}}>
        <h2 className="landing-title-centered">Accès Rapide</h2>
        <p className="landing-subtitle">Naviguez rapidement vers vos espaces de travail</p>
        
        <div className="accueil-carousel">
          {cards.map((card) => (
            <Link
              key={card.to}
              to={card.to}
              className="accueil-card-sq"
            >
              {card.badge && (
                <span className={`accueil-card-badge ${card.badgeColor}`}>
                  {card.badge}
                </span>
              )}

              {/* Colored top accent bar */}
              <div
                className="accueil-card-sq-bar"
                style={{ background: `linear-gradient(90deg, ${card.color}, ${card.color}88)` }}
              />

              <div className="accueil-card-sq-inner">
                <div
                  className="accueil-card-sq-icon"
                  style={{ background: `${card.color}14`, color: card.color }}
                >
                  {card.icon}
                </div>
                <div className="accueil-card-sq-content">
                  <strong>{card.label}</strong>
                  <p>{card.desc}</p>
                </div>
                <span
                  className="accueil-card-sq-arrow"
                  style={{ color: card.color }}
                >
                  <ArrowRight size={22} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </Layout>
  );
}

import {
  ArrowDown, ArrowRight, BarChart3, BrainCircuit, Building2, CheckCircle2,
  CloudSun, KeyRound, Layers3, Moon, PlayCircle, RefreshCw,
  ShieldCheck, Sun, TrendingUp, UserCog,
} from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

function useScrollReveal() {
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("reveal-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    document.querySelectorAll(".reveal-hidden").forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);
}

const floatingCards = [
  { title: "ELT Actif", detail: "Pipeline quotidien", icon: RefreshCw, className: "elt" },
  { title: "Power BI", detail: "Actualisation suivie", icon: BarChart3, className: "bi" },
  { title: "IA Bad Debts", detail: "Prédiction risque", icon: BrainCircuit, className: "ai" },
  { title: "Sécurité", detail: "JWT + MFA", icon: ShieldCheck, className: "security" },
];

const decisionModules = [
  { title: "Power BI", description: "Visualisation des indicateurs SOS Solde & Data.", icon: BarChart3, chart: "bars", accent: "blue" },
  { title: "Machine Learning", description: "Analyse prédictive des mauvaises créances.", icon: BrainCircuit, chart: "line", accent: "violet" },
  { title: "Pipeline ELT SOS Solde & Data", description: "Collecte, transformation et valorisation des flux ADV et REV.", icon: Layers3, chart: "flow", accent: "cyan" },
];

const profiles = [
  ["Super Administrateur", "Tous les modules", "Plateforme complète"],
  ["Administrateur départemental", "Gestion utilisateurs", "Son département"],
  ["Commercial", "Dashboards SOS", "Activité & parc"],
  ["Assurance & Risque", "Bad Debts IA", "Risque client"],
  ["Analyse Opérationnelle", "ELT & dashboards", "Traitements et suivi"],
];

function MiniChart({ type }) {
  if (type === "line") {
    return <div className="b2b-mini-chart b2b-mini-line" aria-hidden="true"><svg viewBox="0 0 240 86" preserveAspectRatio="none"><path d="M4 70 C40 62, 52 66, 78 46 S126 58, 150 32 S198 38, 236 10" /><path className="fill" d="M4 70 C40 62, 52 66, 78 46 S126 58, 150 32 S198 38, 236 10 L236 86 L4 86 Z" /></svg></div>;
  }
  if (type === "flow") {
    const steps = ["ADV + REV", "Extraction", "Chargement Oracle", "Transformation", "Agrégation", "Reporting Power BI"];
    return (
      <div className="b2b-mini-chart b2b-mini-flow" aria-label="Pipeline ELT SOS Solde et Data">
        {steps.map((step, index) => (
          <div className="b2b-flow-step" key={step}>
            <span>{step}</span>
            {index < steps.length - 1 && <ArrowDown size={13} aria-hidden="true" />}
          </div>
        ))}
      </div>
    );
  }
  return <div className="b2b-mini-chart b2b-mini-bars" aria-hidden="true">{[42, 68, 55, 86, 72, 94, 80].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>;
}

export default function AccueilPage() {
  const { user, hasRight } = useAuth();
  useScrollReveal();

  const hour = new Date().getHours();
  const roleLabel = user?.role === "SUPER_ADMIN" ? "Super Administrateur"
    : ["ADMIN", "ADMIN_DEPARTEMENTAL"].includes(user?.role) ? "Administrateur"
      : "Utilisateur";
  const displayName = user?.nom_complet?.trim()?.split(/\s+/)[0] || roleLabel;
  const greeting = hour >= 5 && hour < 12 ? "Bonjour"
    : hour >= 12 && hour < 18 ? "Bon après-midi" : "Bonsoir";
  const GreetingIcon = hour >= 5 && hour < 12 ? Sun
    : hour >= 12 && hour < 18 ? CloudSun : Moon;
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const isAdmin = ["ADMIN", "ADMIN_DEPARTEMENTAL", "SUPER_ADMIN"].includes(user?.role);

  const dashboardPath = hasRight("dashboard_service_sos") ? "/dashboard/service-sos"
    : hasRight("dashboard_parc_service_sos") ? "/dashboard/parc-service-sos"
      : hasRight("dashboard_bad_debts") ? "/dashboard/bad-debts" : "/mon-compte";
  const modules = [
    { title: "Dashboard Service SOS", description: "Analyse des avances, remboursements et services.", icon: BarChart3, to: "/dashboard/service-sos", visible: hasRight("dashboard_service_sos") },
    { title: "Dashboard Parc Service SOS", description: "Suivi du parc prépayé et hybride.", icon: BarChart3, to: "/dashboard/parc-service-sos", visible: hasRight("dashboard_parc_service_sos") },
    { title: "Dashboard Bad Debts", description: "Anticipation des mauvaises créances.", icon: BrainCircuit, to: "/dashboard/bad-debts", visible: hasRight("dashboard_bad_debts") },
    { title: "Traitement ELT", description: "Lancement, suivi et contrôle des traitements.", icon: PlayCircle, to: "/admin/elt", visible: hasRight("lancer_elt") },
    { title: "Utilisateurs", description: "Gestion des comptes et des accès.", icon: UserCog, to: "/admin/users", visible: isSuperAdmin },
    { title: "Départements & permissions", description: "Organisation des rôles par département.", icon: Building2, to: "/admin/departements", visible: isSuperAdmin },
    { title: "Mon département", description: "Gestion des utilisateurs et accès de votre département.", icon: Building2, to: "/admin/mon-departement", visible: isAdmin },
    { title: "Sécurité", description: "Authentification multifacteur et codes de secours.", icon: KeyRound, to: "/security", visible: true },
  ].filter((module) => module.visible);

  return (
    <Layout className="app-shell--home">
      <div className="b2b-home">
        <section className="b2b-hero">
          <div className="b2b-hero-copy">
            <h1 className="b2b-hero-title">Plateforme Décisionnelle SOS Solde &amp; Data</h1>
            <div className="b2b-eyebrow"><GreetingIcon size={16} />{greeting}, {displayName}</div>
            <p className="b2b-hero-description">Pilotez les opérations SOS, supervisez les traitements ELT, analysez les performances Power BI et anticipez les mauvaises créances grâce à l’intelligence artificielle.</p>
            <div className="b2b-hero-actions">
              <Link to={dashboardPath} className="b2b-btn b2b-btn-primary">Accéder aux dashboards <ArrowRight size={17} /></Link>
              {hasRight("lancer_elt") && <Link to="/admin/elt" className="b2b-btn b2b-btn-secondary">Superviser l’ELT <PlayCircle size={17} /></Link>}
            </div>
            <div className="b2b-hero-meta"><CheckCircle2 size={16} />Environnement sécurisé pour {user?.departement_nom || "Tunisie Telecom"}</div>
          </div>

          <div className="b2b-product-stage" aria-label="Aperçu de la plateforme">
            <div className="b2b-product-card">
              <div className="b2b-product-head"><div><span>Tunisie Telecom Platform</span><strong>Vue opérationnelle</strong></div><div className="b2b-live-pill"><span /> En ligne</div></div>
              <div className="b2b-product-kpi"><span>Volume consolidé</span><strong>9 982 474</strong><small>CDR traités <b><TrendingUp size={12} /> +8.4%</b></small></div>
              <div className="b2b-product-chart" aria-hidden="true">{[48, 62, 54, 76, 68, 88, 74, 96, 84, 100].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>
              <div className="b2b-product-stats"><div><strong>24/7</strong><span>Supervision</span></div><div><strong>2</strong><span>Dashboards BI</span></div><div><strong>92%</strong><span>Score IA</span></div></div>
            </div>
            {floatingCards.map(({ title, detail, icon: Icon, className }) => <div key={title} className={`b2b-float-card ${className}`}><span><Icon size={17} /></span><div><strong>{title}</strong><small>{detail}</small></div></div>)}
          </div>
        </section>

        <section className="b2b-section reveal-hidden">
          <div className="b2b-section-heading"><div><span>Espaces de travail</span><h2>Modules intégrés</h2></div><p>Vos espaces de travail disponibles selon vos droits d’accès.</p></div>
          <div className="b2b-modules-grid">
            {modules.map(({ title, description, icon: Icon, to }) => (
              <Link key={title} to={to} className="b2b-module-card"><span className="b2b-module-icon"><Icon size={21} /></span><div><h3>{title}</h3><p>{description}</p></div><ArrowRight className="b2b-module-arrow" size={18} /></Link>
            ))}
          </div>
        </section>

        <section className="b2b-section b2b-decision-section reveal-hidden">
          <div className="b2b-section-heading"><div><span>Chaîne décisionnelle</span><h2>Une plateforme pour piloter les décisions</h2></div><p>Des données brutes jusqu’aux indicateurs et aux modèles prédictifs.</p></div>
          <div className="b2b-decision-grid">
            {decisionModules.map(({ title, description, icon: Icon, chart, accent }) => <article key={title} className={`b2b-decision-card ${accent}`}><div className="b2b-decision-head"><span><Icon size={20} /></span><h3>{title}</h3></div><p>{description}</p><MiniChart type={chart} /></article>)}
          </div>
        </section>

        <section className="b2b-section reveal-hidden">
          <div className="b2b-section-heading"><div><span>Gouvernance</span><h2>Profils & permissions</h2></div><p>Une organisation claire des responsabilités et périmètres d’accès.</p></div>
          <div className="b2b-profile-table-wrap"><table className="b2b-profile-table"><thead><tr><th>Profil</th><th>Accès principal</th><th>Périmètre</th></tr></thead><tbody>{profiles.map(([profile, access, scope]) => <tr key={profile}><td><span className="b2b-profile-mark" />{profile}</td><td>{access}</td><td>{scope}</td></tr>)}</tbody></table></div>
          <div className="b2b-profile-cards">
            {profiles.map(([profile, access, scope]) => (
              <article className="b2b-profile-card" key={profile}>
                <h3><span className="b2b-profile-mark" />{profile}</h3>
                <p><strong>Accès :</strong> {access}</p>
                <p><strong>Périmètre :</strong> {scope}</p>
              </article>
            ))}
          </div>
        </section>

      </div>
    </Layout>
  );
}

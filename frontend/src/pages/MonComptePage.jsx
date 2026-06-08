import {
  Activity, BadgeCheck,
  Building2,
  CalendarDays,
  Clock3,
  CloudSun,
  FileKey2,
  Fingerprint, Mail,
  Moon,
  ShieldCheck,
  Sun,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

const ROLE_LABELS = {
  SUPER_ADMIN: "Super Administrateur Plateforme",
  ADMIN: "Administrateur Départemental",
  ADMIN_DEPARTEMENTAL: "Administrateur Départemental",
  USER: "Employé Départemental",
};

function formatDate(value, compact = false) {
  if (!value) return "Non disponible";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Non disponible";
  return new Intl.DateTimeFormat("fr-FR", compact
    ? { day: "2-digit", month: "short", year: "numeric" }
    : { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
  ).format(date);
}

function formatStatus(value) {
  return String(value || "Non disponible").replace(/_/g, " ").toLowerCase();
}

function ProfileInfoCard({ icon: Icon, label, value }) {
  return (
    <article className="mc-profile-info-card">
      <span><Icon size={18} /></span>
      <div><small>{label}</small><strong>{value || "Non disponible"}</strong></div>
    </article>
  );
}

export default function MonComptePage() {
  const { user } = useAuth();
  const [security, setSecurity] = useState(null);

  useEffect(() => {
    let active = true;
    api.get("/auth/security/recovery-codes/status", { suppressAuthRedirect: true })
      .then((response) => { if (active) setSecurity(response.data); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const hour = new Date().getHours();
  const greeting = hour >= 5 && hour < 12 ? "Bonjour"
    : hour >= 12 && hour < 18 ? "Bon après-midi" : "Bonsoir";
  const GreetingIcon = hour >= 5 && hour < 12 ? Sun : hour >= 12 && hour < 18 ? CloudSun : Moon;
  const firstName = user?.nom_complet?.trim()?.split(/\s+/)[0] || "Utilisateur";
  const roleLabel = ROLE_LABELS[user?.role] || String(user?.role || "Utilisateur").replace(/_/g, " ");
  const accountActive = user?.est_actif !== false && String(user?.statut_compte || "").toUpperCase() === "ACTIF";

  const kpis = [
    { label: "Dernière connexion", value: formatDate(user?.date_derniere_connexion), icon: Clock3, tone: "blue" },
    { label: "Compte créé le", value: formatDate(user?.date_creation, true), icon: CalendarDays, tone: "violet" },
    { label: "Sessions actives", value: "Non disponible", icon: Activity, tone: "cyan" },
    { label: "Codes de secours", value: security ? `${security.codes_restants} restants` : "Non disponible", icon: FileKey2, tone: "green" },
  ];

  return (
    <Layout>
      <div className="mc-profile-page">
        <section className="mc-profile-hero">
          <div className="mc-profile-greeting"><GreetingIcon size={16} />{greeting} {firstName}</div>
          <div className="mc-profile-identity">
            <div className="mc-profile-avatar"><UserRound size={42} /><i /></div>
            <div className="mc-profile-copy">
              <h2>{user?.nom_complet || "Utilisateur"}</h2>
              <p>{roleLabel}</p>
              <span><Building2 size={14} />{user?.departement_nom || "Département non renseigné"}</span>
            </div>
            <div className={`mc-profile-status ${accountActive ? "active" : "inactive"}`}>
              <i />{accountActive ? "Compte actif" : formatStatus(user?.statut_compte)}
            </div>
          </div>
        </section>

        <section className="mc-profile-kpis">
          {kpis.map(({ label, value, icon: Icon, tone }) => (
            <article key={label} className={`mc-profile-kpi ${tone}`}>
              <span><Icon size={19} /></span>
              <div><small>{label}</small><strong>{value}</strong></div>
            </article>
          ))}
        </section>

        <section className="mc-profile-section mc-profile-security">
          <div className="mc-profile-section-head">
            <div><span>Protection personnelle</span><h3>Sécurité du compte</h3></div>
            <ShieldCheck size={20} />
          </div>
          <div className="mc-security-layout">
            <div className="mc-security-score">
              <span><Fingerprint size={24} /></span>
              <div><strong>{security?.total_codes > 0 ? "Protection renforcée" : "État non disponible"}</strong><small>Authentification et récupération du compte</small></div>
            </div>
            <div className="mc-security-list">
              <div><span>MFA</span><strong>{security?.total_codes > 0 ? "Configurée" : "Non disponible"}</strong></div>
              <div><span>Codes de secours</span><strong>{security ? `${security.codes_restants} / ${security.total_codes}` : "Non disponible"}</strong></div>
              <div><span>Dernière connexion</span><strong>{formatDate(user?.date_derniere_connexion)}</strong></div>
            </div>
          </div>
        </section>

        <section className="mc-profile-section">
          <div className="mc-profile-section-head">
            <div><span>Identité professionnelle</span><h3>Informations du compte</h3></div>
            <BadgeCheck size={20} />
          </div>
          <div className="mc-profile-info-grid">
            <ProfileInfoCard icon={UserRound} label="Nom complet" value={user?.nom_complet} />
            <ProfileInfoCard icon={Mail} label="Adresse email" value={user?.email} />
            <ProfileInfoCard icon={ShieldCheck} label="Rôle" value={roleLabel} />
            <ProfileInfoCard icon={Building2} label="Département" value={user?.departement_nom} />
          </div>
        </section>
      </div>
    </Layout>
  );
}

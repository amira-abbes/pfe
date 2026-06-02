import { BadgeCheck, Building2, CalendarDays, Clock, Mail, Shield, UserRound } from "lucide-react";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

function formatDate(value) {
  if (!value) return "Non disponible";
  try {
    return new Intl.DateTimeFormat("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return "Non disponible";
  }
}

function formatStatus(value) {
  const raw = String(value || "").trim();
  if (!raw) return "Non disponible";
  return raw.replace(/_/g, " ");
}

function InfoRow({ icon, label, value }) {
  return (
    <div className="mc-info-row">
      <div className="mc-info-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value || "Non disponible"}</strong>
      </div>
    </div>
  );
}

export default function MonComptePage() {
  const { user } = useAuth();

  return (
    <Layout title="Mon compte" subtitle="Informations personnelles du compte connecté">
      <section className="mc-account-panel">
        <div className="mc-account-head">
          <div className="mc-account-avatar">
            <UserRound size={34} />
          </div>
          <div>
            <h2>{user?.nom_complet || "Utilisateur"}</h2>
            <p>{user?.email || "Email non disponible"}</p>
          </div>
        </div>

        <div className="mc-info-grid">
          <InfoRow icon={<UserRound size={20} />} label="Nom et prénom" value={user?.nom_complet} />
          <InfoRow icon={<Mail size={20} />} label="Email" value={user?.email} />
          <InfoRow icon={<Shield size={20} />} label="Rôle" value={user?.role} />
          <InfoRow icon={<Building2 size={20} />} label="Département" value={user?.departement_nom} />
          <InfoRow icon={<BadgeCheck size={20} />} label="Statut du compte" value={formatStatus(user?.statut_compte)} />
          <InfoRow icon={<CalendarDays size={20} />} label="Date de création" value={formatDate(user?.date_creation)} />
          <InfoRow icon={<Clock size={20} />} label="Dernière connexion" value={formatDate(user?.date_derniere_connexion)} />
        </div>
      </section>
    </Layout>
  );
}

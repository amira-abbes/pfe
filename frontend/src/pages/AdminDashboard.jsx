import { BarChart3, Building2, PlayCircle, Users } from "lucide-react";
import { Link } from "react-router-dom";

import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

export default function AdminDashboard() {
  const { hasRight } = useAuth();

  return (
    <Layout
      title="Dashboard administrateur"
      subtitle="Pilotage des utilisateurs, permissions, départements et traitements ELT."
    >
      <div className="grid grid-3">
        {hasRight("gerer_utilisateurs") && (
          <Link className="stat-card" to="/admin/users">
            <Users size={28} />
            <strong>Utilisateurs</strong>
            <span>Création et gestion des comptes</span>
          </Link>
        )}

        {(hasRight("gerer_departements") || hasRight("gerer_roles")) && (
          <Link className="stat-card" to="/admin/departements">
            <Building2 size={28} />
            <strong>Départements & permissions</strong>
            <span>Droits d'accès par département</span>
          </Link>
        )}

        {hasRight("dashboard_service_sos") && (
          <Link className="stat-card" to="/dashboard/service-sos">
            <BarChart3 size={28} />
            <strong>Dashboard Service SOS</strong>
            <span>Consultation Power BI sécurisée</span>
          </Link>
        )}

        {hasRight("lancer_elt") && (
          <Link className="stat-card" to="/admin/elt">
            <PlayCircle size={28} />
            <strong>Traitement ELT</strong>
            <span>Lancement ELT et consultation des rapports</span>
          </Link>
        )}
      </div>
    </Layout>
  );
}

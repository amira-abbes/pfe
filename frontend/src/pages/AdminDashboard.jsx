import { Building2, PlayCircle, ShieldCheck, Users } from "lucide-react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

export default function AdminDashboard() {
  const { user } = useAuth();

  return (
    <Layout
      title="Dashboard administrateur"
      subtitle="Pilotage des utilisateurs, permissions, départements et actions sensibles."
    >
      <div className="grid grid-3">
        <Link className="stat-card" to="/admin/users">
          <Users size={28} />
          <strong>Utilisateurs</strong>
          <span>Création et gestion des comptes</span>
        </Link>

        <Link className="stat-card" to="/admin/departements">
          <Building2 size={28} />
          <strong>Départements & permissions</strong>
          <span>Droits d’accès par département</span>
        </Link>

        <Link className="stat-card" to="/admin/elt">
          <PlayCircle size={28} />
          <strong>Traitement ELT</strong>
          <span>Action sensible protégée</span>
        </Link>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>État sécurité admin</h2>
        <div className={user?.webauthn_admin_active ? "alert alert-success" : "alert alert-error"}>
          <ShieldCheck size={16} />
          {user?.webauthn_admin_active
            ? "WebAuthn est configuré pour les actions sensibles."
            : "WebAuthn n’est pas encore configuré. Les actions sensibles demanderont une configuration."}
        </div>
      </div>
    </Layout>
  );
}

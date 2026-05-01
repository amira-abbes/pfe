import { KeyRound, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

export default function UserDashboard() {
  const { user } = useAuth();
  const [securityStatus, setSecurityStatus] = useState(null);
  const [securityUnavailable, setSecurityUnavailable] = useState(false);

  useEffect(() => {
    async function loadSecurityStatus() {
      try {
        const response = await api.get("/auth/security/recovery-codes/status", {
          skipAuthRedirect: true,
        });
        setSecurityStatus(response.data);
      } catch {
        setSecurityUnavailable(true);
      }
    }

    loadSecurityStatus();
  }, []);

  return (
    <Layout
      title="Dashboard utilisateur"
      subtitle="Espace personnel sécurisé par mot de passe et Authenticator."
    >
      <div className="grid grid-2">
        <div className="card">
          <h2>Bienvenue</h2>
          <p>
            Bonjour <strong>{user?.nom_complet}</strong>, votre session est active.
          </p>

          <div className="info-row">
            <UserRound size={18} />
            <span>{user?.email}</span>
          </div>

          <div className="info-row">
            <ShieldCheck size={18} />
            <span>Compte : {user?.statut_compte}</span>
          </div>
        </div>

        <div className="card">
          <h2>Sécurité du compte</h2>
          <p>
            Votre compte utilise une authentification forte avec mot de passe et
            code TOTP.
          </p>

          <div className="mini-stat">
            <strong>
              {securityStatus ? securityStatus.codes_restants : "-"}
            </strong>
            <span>Codes de secours restants</span>
          </div>

          {securityUnavailable && (
            <div className="alert alert-info">
              Consultez votre espace sécurité pour gérer vos codes de secours.
            </div>
          )}

          <Link to="/security" className="btn btn-primary">
            <KeyRound size={18} />
            Gérer mes codes de secours
          </Link>
        </div>
      </div>
    </Layout>
  );
}

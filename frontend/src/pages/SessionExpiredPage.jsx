import { Clock } from "lucide-react";
import { Link } from "react-router-dom";

export default function SessionExpiredPage() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Session expirée</h1>
        <p>Votre session a expiré pour des raisons de sécurité.</p>

        <div className="alert alert-error">
          <Clock size={16} /> Session expirée. Veuillez vous reconnecter.
        </div>

        <div className="form">
          <Link className="btn btn-primary" to="/login">
            Retour à la connexion
          </Link>
        </div>
      </div>
    </div>
  );
}
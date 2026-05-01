import { Link } from "react-router-dom";

export default function AccessDeniedPage() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>Accès refusé</h1>
        <p>Vous n'êtes pas autorisé à accéder à cette page.</p>
        <Link className="btn btn-primary" to="/login">
          Retour à la connexion
        </Link>
      </div>
    </div>
  );
}

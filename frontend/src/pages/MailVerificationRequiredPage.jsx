import { Link } from "react-router-dom";

export default function MailVerificationRequiredPage() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>Connexion refusée</h1>
        <p>
          Vous ne pouvez plus vous connecter directement. Veuillez vérifier votre
          boîte mail et suivre les instructions de sécurité.
        </p>
        <Link className="btn btn-primary" to="/login">
          Retour à la connexion
        </Link>
      </div>
    </div>
  );
}

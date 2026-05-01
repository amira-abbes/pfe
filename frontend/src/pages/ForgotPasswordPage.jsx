import { Mail } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, getApiError } from "../api/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [debugLink, setDebugLink] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setDebugLink("");
    setLoading(true);

    try {
      const response = await api.post("/auth/password-reset/request", { email });
      setMessage(response.data.message);
      setDebugLink(response.data.reset_link_debug || "");
    } catch (err) {
      setError(getApiError(err, "Erreur lors de la demande."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Mot de passe oublié</h1>
        <p>Entrez votre email pour recevoir un lien de réinitialisation.</p>

        {error && <div className="alert alert-error">{error}</div>}
        {message && <div className="alert alert-success">{message}</div>}

        {debugLink && (
          <div className="alert alert-info">
            Mode debug : <br />
            <Link to={debugLink.replace(window.location.origin, "")}>{debugLink}</Link>
          </div>
        )}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <label>Email</label>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>

          <button className="btn btn-primary" disabled={loading}>
            <Mail size={18} />
            {loading ? "Envoi en cours" : "Envoyer le lien"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Retour connexion</Link>
        </div>
      </div>
    </div>
  );
}
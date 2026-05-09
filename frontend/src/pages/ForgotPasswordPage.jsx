import { ArrowRight, Mail } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, getApiError } from "../api/api";
import "../styles/auth_redesign.css";

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
        <div className="auth-tagline">La vie est émotions</div>

        <h1>Récupération</h1>
        <div className="rainbow-underline"></div>

        <p style={{ marginBottom: '24px', textAlign: 'left', color: '#64748b', fontSize: '14px' }}>
          Entrez votre email pour recevoir un lien de réinitialisation.
        </p>

        {error && <div className="alert-error">{error}</div>}
        {message && <div className="alert-error" style={{ background: '#ecfdf3', color: '#027a48' }}>{message}</div>}

        {debugLink && (
          <div className="alert-error" style={{ background: '#eff8ff', color: '#175cd3' }}>
            <Link to={debugLink.replace(window.location.origin, "")} style={{ color: 'inherit' }}>Lien direct (Mode Debug)</Link>
          </div>
        )}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Mail size={18} /></span>
              <input
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="votre.email@gmail.com"
                required
              />
            </div>
          </div>

          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? "Envoi..." : "Envoyer le lien"}
            {!loading && (
              <div className="btn-arrow-circle">
                <ArrowRight size={18} />
              </div>
            )}
          </button>
        </form>

        <div className="auth-links" style={{ marginTop: '24px' }}>
          <Link to="/login" style={{ textDecoration: 'none', color: '#2563eb', fontWeight: 600, fontSize: '14px' }}>
            Retour connexion
          </Link>
        </div>
      </div>
    </div>
  );
}
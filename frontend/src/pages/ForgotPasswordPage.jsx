import { Mail, ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, getApiError } from "../api/api";
import AuthTriangles from "../components/AuthTriangles";

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
      <AuthTriangles />

      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Mot de passe oublié</h1>
        <div className="rainbow-line" />

        <p style={{
          textAlign: 'left',
          marginBottom: '24px',
          fontSize: '14px',
          color: '#64748b',
          lineHeight: '1.6',
          fontWeight: '400',
          letterSpacing: '0.01em',
          borderLeft: '3px solid #3b82f6',
          paddingLeft: '12px',
          background: 'rgba(59,130,246,0.04)',
          borderRadius: '0 8px 8px 0',
          padding: '10px 12px',
        }}>
          Entrez votre adresse e-mail pour recevoir un lien de réinitialisation sécurisé.
        </p>

        {error && <div className="auth-error-banner">{error}</div>}
        {message && <div className="auth-error-banner" style={{ background: '#ecfdf5', borderColor: '#d1fae5', color: '#065f46' }}>{message}</div>}

        {debugLink && (
          <div className="auth-error-banner" style={{ background: '#f0f9ff', borderColor: '#e0f2fe', color: '#0369a1' }}>
            Mode debug : <br />
            <Link to={debugLink.replace(window.location.origin, "")} style={{ textDecoration: 'underline' }}>{debugLink}</Link>
          </div>
        )}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Mail size={17} /></span>
              <input
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="Votre adresse e-mail"
                required
              />
            </div>
          </div>

          <button className="btn-primary" disabled={loading}>
            {loading ? "Envoi..." : "Envoyer le lien"}
            {!loading && <ArrowRight size={18} />}
          </button>
        </form>

        <div className="auth-forgot" style={{ textAlign: 'center', marginTop: '24px' }}>
          <Link to="/login">Retour à la connexion</Link>
        </div>
      </div>
    </div>
  );
}
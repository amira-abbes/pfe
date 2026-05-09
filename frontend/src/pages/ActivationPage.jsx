import { ArrowRight, Eye, EyeOff, Lock, Mail } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import "../styles/auth_redesign.css";

export default function ActivationPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const token = params.get("token");

  const [email, setEmail] = useState("");
  const [resendEmail, setResendEmail] = useState("");
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Vérification du lien...");
  const [error, setError] = useState("");

  const [resendMessage, setResendMessage] = useState("");
  const [resendCode, setResendCode] = useState("");

  const [form, setForm] = useState({
    nouveau_mot_de_passe: "",
    confirmation_mot_de_passe: "",
  });

  const [loading, setLoading] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const accountNotPending =
    resendCode === "ACCOUNT_ALREADY_ACTIVE" ||
    resendCode === "ACCOUNT_MFA_SETUP_REQUIRED" ||
    resendCode === "ACCOUNT_NOT_PENDING_ACTIVATION";

  const showInvalidLinkMessage = status === "error" && !accountNotPending;

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  useEffect(() => {
    async function verify() {
      try {
        if (!token) {
          setStatus("error");
          setMessage("Lien d’activation manquant ou invalide.");
          return;
        }

        const response = await api.get(
          `/auth/activation/verify?token=${encodeURIComponent(token)}`
        );

        const data = response.data;

        if (!data.success) {
          setStatus("error");
          setMessage(data.message);
          return;
        }

        setEmail(data.email);
        setResendEmail(data.email || "");
        setStatus("success");
        setMessage(data.message);
      } catch (err) {
        setStatus("error");
        setMessage(getApiError(err, "Lien invalide ou expiré."));
      }
    }

    verify();
  }, [token]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await api.post("/auth/activation/complete", {
        token,
        nouveau_mot_de_passe: form.nouveau_mot_de_passe,
        confirmation_mot_de_passe: form.confirmation_mot_de_passe,
      });

      const data = response.data;

      sessionStorage.setItem("totp_setup_token", data.totp_setup_token);
      sessionStorage.setItem("activation_email", data.email);

      navigate("/activation/totp");
    } catch (err) {
      setError(getApiError(err, "Erreur lors de l’activation."));
    } finally {
      setLoading(false);
    }
  }

  async function handleResend(event) {
    event.preventDefault();

    setError("");
    setResendMessage("");
    setResendCode("");
    setResendLoading(true);

    try {
      const response = await api.post("/auth/activation/resend", {
        email: resendEmail,
      });

      const data = response.data;

      setResendMessage(data.message);
      setResendCode(data.code || "");

      if (
        data.code === "ACCOUNT_ALREADY_ACTIVE" ||
        data.code === "ACCOUNT_MFA_SETUP_REQUIRED" ||
        data.code === "ACCOUNT_NOT_PENDING_ACTIVATION"
      ) {
        setMessage("");
      }
    } catch (err) {
      setError(getApiError(err, "Erreur lors de la demande de nouveau lien."));
    } finally {
      setResendLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <div className="auth-tagline">La vie est émotions</div>

        <h1>Activation</h1>
        <div className="rainbow-underline"></div>

        {status === "loading" && <p style={{ marginTop: '20px', textAlign: 'center', color: '#64748b' }}>{message}</p>}

        {showInvalidLinkMessage && (
          <div className="alert-error" style={{ marginTop: '20px' }}>{message}</div>
        )}

        {status === "error" && !accountNotPending && (
          <form className="form" onSubmit={handleResend} style={{ marginTop: '20px' }}>
            <div className="input-group">
              <div className="input-icon-wrap">
                <span className="input-icon-left"><Mail size={18} /></span>
                <input
                  className="input"
                  type="email"
                  value={resendEmail}
                  onChange={(event) => setResendEmail(event.target.value)}
                  placeholder="votre.email@gmail.com"
                  required
                />
              </div>
            </div>

            <button className="btn-primary" disabled={resendLoading}>
              {resendLoading ? "Envoi..." : "Nouveau lien"}
              {!resendLoading && (
                <div className="btn-arrow-circle">
                  <ArrowRight size={18} />
                </div>
              )}
            </button>
          </form>
        )}

        {resendMessage && (
          <div
            className="alert-error"
            style={{ 
              marginTop: '20px',
              background: accountNotPending ? '#eff8ff' : '#ecfdf3', 
              color: accountNotPending ? '#175cd3' : '#027a48' 
            }}
          >
            {resendMessage}
          </div>
        )}

        {accountNotPending && (
          <div className="form" style={{ marginTop: '20px' }}>
            <Link className="btn-primary" to="/forgot-password">
              Réinitialiser mot de passe
              <div className="btn-arrow-circle">
                <ArrowRight size={18} />
              </div>
            </Link>

            <Link className="btn-primary" to="/login" style={{ background: 'transparent', color: '#1e3a8a', border: '2px solid #3b82f6', boxShadow: 'none' }}>
              Se connecter
            </Link>
          </div>
        )}

        {error && <div className="alert-error" style={{ marginTop: '20px' }}>{error}</div>}

        {status === "success" && (
          <div style={{ marginTop: '20px' }}>
            <p style={{ color: '#64748b', fontSize: '14px', marginBottom: '24px' }}>{message}</p>

            <form className="form" onSubmit={handleSubmit}>
              <div className="input-group">
                <div className="input-icon-wrap">
                  <span className="input-icon-left"><Lock size={18} /></span>
                  <input
                    className="input has-right-icon"
                    type={showPassword ? "text" : "password"}
                    value={form.nouveau_mot_de_passe}
                    onChange={(event) =>
                      updateField("nouveau_mot_de_passe", event.target.value)
                    }
                    placeholder="Nouveau mot de passe"
                    required
                  />
                  <button
                    type="button"
                    className="input-icon-right"
                    onClick={() => setShowPassword((v) => !v)}
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <div className="input-group">
                <div className="input-icon-wrap">
                  <span className="input-icon-left"><Lock size={18} /></span>
                  <input
                    className="input has-right-icon"
                    type={showConfirmPassword ? "text" : "password"}
                    value={form.confirmation_mot_de_passe}
                    onChange={(event) =>
                      updateField("confirmation_mot_de_passe", event.target.value)
                    }
                    placeholder="Confirmer"
                    required
                  />
                  <button
                    type="button"
                    className="input-icon-right"
                    onClick={() => setShowConfirmPassword((v) => !v)}
                    tabIndex={-1}
                  >
                    {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <button className="btn-primary" disabled={loading}>
                {loading ? "Activation..." : "Créer le mot de passe"}
                {!loading && (
                  <div className="btn-arrow-circle">
                    <ArrowRight size={18} />
                  </div>
                )}
              </button>
            </form>
          </div>
        )}

        {!accountNotPending && (
          <div className="auth-links" style={{ marginTop: '24px' }}>
            <Link to="/login" style={{ textDecoration: 'none', color: '#2563eb', fontWeight: 600, fontSize: '14px' }}>
              Retour connexion
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
import { Eye, EyeOff, KeyRound, LogIn, Mail, Lock, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import AuthTriangles from "../components/AuthTriangles";

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
      <AuthTriangles />

      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Activation</h1>
        <div className="rainbow-line" />

        {status === "loading" && <p className="subtitle" style={{ textAlign: 'center' }}>{message}</p>}

        {email && !error && (
          <div style={{ textAlign: 'center', marginBottom: '20px', fontSize: '13px', color: '#64748b' }}>
            Compte : <strong>{email}</strong>
          </div>
        )}

        {showInvalidLinkMessage && (
          <div className="auth-error-banner">{message}</div>
        )}

        {status === "error" && !accountNotPending && (
          <form className="form" onSubmit={handleResend}>
            <p className="subtitle" style={{ textAlign: 'center' }}>Lien expiré ou invalide. Demandez-en un nouveau :</p>
            <div className="input-group">
              <div className="input-icon-wrap">
                <span className="input-icon-left"><Mail size={17} /></span>
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
              {resendLoading ? "Envoi..." : "Demander un nouveau lien"}
              {!resendLoading && <ArrowRight size={18} />}
            </button>
          </form>
        )}

        {resendMessage && (
          <div className="auth-error-banner" style={{ background: accountNotPending ? '#f0f9ff' : '#ecfdf5', borderColor: accountNotPending ? '#e0f2fe' : '#d1fae5', color: accountNotPending ? '#0369a1' : '#065f46' }}>
            {resendMessage}
          </div>
        )}

        {accountNotPending && (
          <div className="form" style={{ marginTop: '16px' }}>
            <Link className="btn-primary" to="/forgot-password" style={{ textDecoration: 'none' }}>
              Réinitialiser le mot de passe
              <KeyRound size={18} />
            </Link>

            <Link className="btn-ghost" to="/login" style={{ textDecoration: 'none' }}>
              Se connecter
              <LogIn size={18} />
            </Link>
          </div>
        )}

        {error && <div className="auth-error-banner">{error}</div>}

        {status === "success" && (
          <>
            <p className="subtitle" style={{ textAlign: 'center', marginBottom: '24px' }}>
              Configurez votre mot de passe pour activer votre compte.
            </p>

            <form className="form" onSubmit={handleSubmit}>
              <div className="input-group">
                <div className="input-icon-wrap">
                  <span className="input-icon-left"><Lock size={17} /></span>
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
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>

              <div className="input-group">
                <div className="input-icon-wrap">
                  <span className="input-icon-left"><Lock size={17} /></span>
                  <input
                    className="input has-right-icon"
                    type={showConfirmPassword ? "text" : "password"}
                    value={form.confirmation_mot_de_passe}
                    onChange={(event) =>
                      updateField("confirmation_mot_de_passe", event.target.value)
                    }
                    placeholder="Confirmer le mot de passe"
                    required
                  />
                  <button
                    type="button"
                    className="input-icon-right"
                    onClick={() => setShowConfirmPassword((v) => !v)}
                    tabIndex={-1}
                  >
                    {showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>

              <button className="btn-primary" disabled={loading}>
                {loading ? "Activation..." : "Activer mon compte"}
                {!loading && <ArrowRight size={18} />}
              </button>
            </form>
          </>
        )}

        {!accountNotPending && (
          <div className="auth-forgot" style={{ textAlign: 'center', marginTop: '24px' }}>
            <Link to="/login">Retour à la connexion</Link>
          </div>
        )}
      </div>
    </div>
  );
}
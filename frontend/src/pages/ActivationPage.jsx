import { KeyRound, LogIn, Mail, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

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

        <h1>Activation du compte</h1>

        {status === "loading" && <p>{message}</p>}

        {email && <div className="alert alert-info">Compte : {email}</div>}

        {showInvalidLinkMessage && (
          <div className="alert alert-error">{message}</div>
        )}

        {status === "error" && !accountNotPending && (
          <form className="form" onSubmit={handleResend}>
            <div className="input-group">
              <label>Email du compte</label>
              <input
                className="input"
                type="email"
                value={resendEmail}
                onChange={(event) => setResendEmail(event.target.value)}
                placeholder="votre.email@gmail.com"
                required
              />
            </div>

            <button className="btn btn-primary" disabled={resendLoading}>
              <Mail size={18} />
              {resendLoading ? "Envoi en cours" : "Demander un nouveau lien"}
            </button>
          </form>
        )}

        {resendMessage && (
          <div
            className={
              accountNotPending ? "alert alert-info" : "alert alert-success"
            }
          >
            {resendMessage}
          </div>
        )}

        {accountNotPending && (
          <div className="form">
            <Link className="btn btn-primary" to="/forgot-password">
              <KeyRound size={18} />
              Réinitialiser mot de passe
            </Link>

            <Link className="btn btn-secondary" to="/login">
              <LogIn size={18} />
              Se connecter
            </Link>
          </div>
        )}

        {error && <div className="alert alert-error">{error}</div>}

        {status === "success" && (
          <>
            <p>{message}</p>

            <form className="form" onSubmit={handleSubmit}>
              <div className="input-group">
                <label>Nouveau mot de passe</label>
                <input
                  className="input"
                  type="password"
                  value={form.nouveau_mot_de_passe}
                  onChange={(event) =>
                    updateField("nouveau_mot_de_passe", event.target.value)
                  }
                  required
                />
              </div>

              <div className="input-group">
                <label>Confirmation</label>
                <input
                  className="input"
                  type="password"
                  value={form.confirmation_mot_de_passe}
                  onChange={(event) =>
                    updateField("confirmation_mot_de_passe", event.target.value)
                  }
                  required
                />
              </div>

              <button className="btn btn-primary" disabled={loading}>
                <Save size={18} />
                {loading ? "Activation en cours" : "Créer le mot de passe"}
              </button>
            </form>
          </>
        )}

        {!accountNotPending && (
          <div className="auth-links">
            <Link to="/login">Retour connexion</Link>
          </div>
        )}
      </div>
    </div>
  );
}
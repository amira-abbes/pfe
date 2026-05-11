import { ShieldCheck, KeyRound, ArrowRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import AuthTriangles from "../components/AuthTriangles";

export default function PasswordResetVerifyPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const token = params.get("token");
  const fromLockout = useMemo(
    () => window.location.pathname.includes("from-lockout"),
    []
  );

  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Vérification du lien en cours.");
  const [email, setEmail] = useState("");

  useEffect(() => {
    async function verify() {
      try {
        if (!token) {
          setStatus("expired");
          setMessage("Lien de réinitialisation expiré.");
          return;
        }

        const response = await api.post("/auth/password-reset/verify", { token });
        const data = response.data;

        if (!data.success) {
          setStatus(data.code === "PASSWORD_RESET_LINK_INVALID" ? "expired" : "error");
          setMessage(data.message || "Lien de réinitialisation expiré.");
          return;
        }

        sessionStorage.setItem("reset_mfa_token", data.reset_mfa_token);
        sessionStorage.setItem("reset_email", data.email);

        setEmail(data.email);
        setStatus("success");
        setMessage("Veuillez confirmer votre identité pour continuer.");
      } catch (err) {
        setStatus("error");
        setMessage(getApiError(err, "Lien invalide ou expiré."));
      }
    }

    verify();
  }, [token]);

  const title = fromLockout ? "Réinitialisation sécurisée" : "Réinitialisation du mot de passe";

  return (
    <div className="auth-page">
      <AuthTriangles />

      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>
          {status === "expired" ? "Lien expiré" : title}
        </h1>
        <div className="rainbow-line" />

        {(status === "loading" || status === "success") && (
          <p className="subtitle" style={{ textAlign: 'center', marginBottom: '24px' }}>
            {message}
          </p>
        )}

        {email && !status.includes('error') && (
          <div style={{ textAlign: 'center', marginBottom: '20px', fontSize: '13px', color: '#64748b' }}>
            Compte : <strong>{email}</strong>
          </div>
        )}

        {status === "error" && <div className="auth-error-banner">{message}</div>}
        
        {status === "expired" && (
          <div className="auth-error-banner" style={{ background: '#f8fafc', color: '#64748b', border: '1px solid #e2e8f0', boxShadow: 'none' }}>
            Ce lien n’est plus valide. Vous pouvez demander un nouveau lien de réinitialisation.
          </div>
        )}

        {status === "success" && (
          <div className="form">
            <button
              className="btn-primary"
              onClick={() => {
                sessionStorage.setItem("reset_mfa_mode", "totp");
                navigate("/password-reset/mfa");
              }}
            >
              Vérifier avec Authenticator
              <ShieldCheck size={18} />
            </button>

            <button
              className="btn-ghost"
              onClick={() => {
                sessionStorage.setItem("reset_mfa_mode", "recovery");
                navigate("/password-reset/mfa");
              }}
            >
              <KeyRound size={18} />
              Utiliser un code de secours
            </button>
          </div>
        )}

        {status === "expired" && (
          <div className="form">
            <Link to="/forgot-password" className="btn-primary" style={{ textDecoration: 'none' }}>
              Demander un nouveau lien
              <ArrowRight size={18} />
            </Link>
          </div>
        )}

        <div className="auth-forgot" style={{ textAlign: 'center', marginTop: '24px', justifyContent: 'center' }}>
          <Link to="/login">Retour à la connexion</Link>
        </div>
      </div>
    </div>
  );
}

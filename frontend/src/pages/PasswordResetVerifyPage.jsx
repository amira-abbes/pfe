import { ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

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
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>
          {status === "expired" ? "Lien de réinitialisation expiré" : title}
        </h1>

        {status === "loading" && <p>{message}</p>}
        {status === "success" && <p>{message}</p>}

        {email && <div className="alert alert-info">Compte : {email}</div>}

        {status === "error" && <div className="alert alert-error">{message}</div>}
        {status === "expired" && (
          <div className="blocked-box">
            <h2>Lien de réinitialisation expiré</h2>
            <p>
              Ce lien n’est plus valide. Vous pouvez demander un nouveau lien
              de réinitialisation.
            </p>
          </div>
        )}

        {status === "success" && (
          <div className="form">
            <button
              className="btn btn-primary"
              onClick={() => {
                sessionStorage.setItem("reset_mfa_mode", "totp");
                navigate("/password-reset/mfa");
              }}
            >
              <ShieldCheck size={18} />
              Vérifier avec Authenticator
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => {
                sessionStorage.setItem("reset_mfa_mode", "recovery");
                navigate("/password-reset/mfa");
              }}
            >
              Utiliser un code de secours
            </button>
          </div>
        )}

        {status === "expired" && (
          <div className="form">
            <Link to="/forgot-password" className="btn btn-primary">
              Demander un nouveau lien
            </Link>
          </div>
        )}

        <div className="auth-links">
          <Link to="/login">Retour à la connexion</Link>
        </div>
      </div>
    </div>
  );
}

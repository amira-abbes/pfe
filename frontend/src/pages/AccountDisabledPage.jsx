import { ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

export default function AccountDisabledPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const email = location.state?.email || "";
  const role = String(location.state?.role || "USER").toUpperCase();
  const reason = location.state?.reason || searchParams.get("reason") || "account_disabled";
  const initialMessage = location.state?.message || searchParams.get("message") || "";
  const canRequest = location.state?.can_request_reactivation !== false;

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [requestSent, setRequestSent] = useState(false);

  const copy = useMemo(() => {
    if (reason === "account_blocked") {
      return {
        title: "Compte bloqué",
        message:
          "Votre compte est bloqué après plusieurs tentatives de connexion. Contactez un administrateur.",
      };
    }
    if (reason === "account_pending_first_login") {
      return {
        title: "Compte en attente",
        message: "Votre compte est en attente de première connexion.",
      };
    }
    if (reason === "account_deleted") {
      return {
        title: "Compte indisponible",
        message: "Ce compte n’est plus disponible.",
      };
    }
    if (role === "ADMIN") {
      return {
        title: "Compte administrateur désactivé",
        message:
          "Votre compte administrateur est désactivé. Veuillez contacter le super administrateur pour le réactiver.",
      };
    }
    return {
      title: "Compte désactivé",
      message:
        "Votre compte est désactivé. Veuillez contacter l’administrateur de votre département pour le réactiver.",
    };
  }, [reason, role]);

  async function requestReactivation() {
    setError("");
    setMessage("");
    if (!email) {
      setError("Email du compte introuvable. Veuillez recommencer la connexion.");
      return;
    }
    setLoading(true);
    try {
      const response = await api.post(
        "/auth/account-reactivation/request",
        { email },
        { skipAuthRedirect: true }
      );
      const data = response.data;
      if (data.success) {
        setMessage(data.message || "Votre demande de réactivation a été envoyée.");
        setRequestSent(true);
      } else {
        setError(data.message || "La demande de réactivation n’a pas pu être envoyée.");
      }
    } catch (err) {
      setError(getApiError(err, "La demande de réactivation n’a pas pu être envoyée."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>{copy.title}</h1>
        <p>{initialMessage || copy.message}</p>

        {message && <div className="alert alert-success">{message}</div>}
        {error && <div className="alert alert-error">{error}</div>}

        <div className="form">
          {canRequest && ["account_disabled", "account_blocked"].includes(reason) && (
            <button
              className="btn btn-primary"
              type="button"
              onClick={requestReactivation}
              disabled={loading || requestSent}
            >
              <ShieldAlert size={18} />
              {loading ? "Envoi en cours..." : "Demander la réactivation"}
            </button>
          )}
          <Link className="btn btn-secondary" to="/login">
            Retour à la connexion
          </Link>
        </div>
      </div>
    </div>
  );
}

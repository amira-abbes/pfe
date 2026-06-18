import { ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

const ACCOUNT_DISABLED_CONTEXT_KEY = "account_disabled_context";

function readStoredContext() {
  try {
    return JSON.parse(sessionStorage.getItem(ACCOUNT_DISABLED_CONTEXT_KEY)) || {};
  } catch {
    sessionStorage.removeItem(ACCOUNT_DISABLED_CONTEXT_KEY);
    return {};
  }
}

export default function AccountDisabledPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const storedContext = readStoredContext();
  const email = location.state?.email || storedContext.email || "";
  const role = String(location.state?.role || storedContext.role || "USER").toUpperCase();
  const reason =
    location.state?.reason ||
    searchParams.get("reason") ||
    storedContext.reason ||
    "account_disabled";
  const initialMessage =
    location.state?.message ||
    searchParams.get("message") ||
    storedContext.message ||
    "";
  const canRequest =
    location.state?.can_request_reactivation ??
    storedContext.can_request_reactivation ??
    true;
  const isSuperAdminBlocked = role === "SUPER_ADMIN" && reason === "account_blocked";
  const canShowRequestButton = Boolean(canRequest) && !isSuperAdminBlocked;

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [requestSent, setRequestSent] = useState(false);

  useEffect(() => {
    if (!email) return;
    sessionStorage.setItem(
      ACCOUNT_DISABLED_CONTEXT_KEY,
      JSON.stringify({
        email,
        role,
        reason,
        message: initialMessage,
        can_request_reactivation: canRequest,
      })
    );
  }, [email, role, reason, initialMessage, canRequest]);

  const copy = useMemo(() => {
    if (reason === "account_blocked") {
      if (role === "SUPER_ADMIN") {
        return {
          title: "Compte bloqué",
          message:
            "Votre compte est bloqué après plusieurs tentatives de connexion.\n\nVeuillez réactiver votre compte à l’aide du lien sécurisé envoyé à votre adresse e-mail.",
        };
      }
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

  const displayMessage = isSuperAdminBlocked ? copy.message : initialMessage || copy.message;

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
      const data = response.data || {};

      if (data.status === "created" || data.status === "already_pending") {
        setMessage(data.message || "Votre demande de réactivation a été envoyée.");
        setRequestSent(true);
        return;
      }

      const fallbackByStatus = {
        no_recipient:
          "Aucun administrateur actif n’est disponible pour traiter cette demande.",
        email_failed:
          "La demande n’a pas pu être envoyée par email. Veuillez réessayer.",
        invalid_user: "Ce compte ne peut pas demander une réactivation.",
      };
      setError(
        data.message ||
          fallbackByStatus[data.status] ||
          "La demande de réactivation n’a pas pu être envoyée."
      );
    } catch (err) {
      setError(
        getApiError(err, "La demande de réactivation n’a pas pu être envoyée.")
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>{copy.title}</h1>
        <p style={{ whiteSpace: "pre-line" }}>{displayMessage}</p>

        {message && <div className="alert alert-success">{message}</div>}
        {error && <div className="alert alert-error">{error}</div>}

        <div className="form">
          {canShowRequestButton && ["account_disabled", "account_blocked"].includes(reason) && (
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
          <Link
            className="btn btn-secondary"
            to="/login"
            onClick={() => sessionStorage.removeItem(ACCOUNT_DISABLED_CONTEXT_KEY)}
          >
            Retour à la connexion
          </Link>
        </div>
      </div>
    </div>
  );
}

import { CheckCircle2, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

const COPY = {
  reactivate: {
    title: "Réactiver ce compte ?",
    description: "Cette action réactivera le compte et réinitialisera ses blocages de sécurité.",
    button: "Réactiver le compte",
    icon: CheckCircle2,
  },
  ignore: {
    title: "Ignorer cette demande ?",
    description: "Cette action laissera le compte désactivé.",
    button: "Ignorer la demande",
    icon: XCircle,
  },
};

const SUCCESS_STATUSES = new Set(["reactivated", "ignored", "success"]);

export default function ReactivationActionPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const action = useMemo(() => String(searchParams.get("action") || "").toLowerCase(), [searchParams]);
  const copy = COPY[action];

  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const [canResend, setCanResend] = useState(false);
  const [resendMessage, setResendMessage] = useState("");

  async function executeAction() {
    if (!token || !copy) {
      setDone(true);
      setStatus("invalid");
      setMessage("Lien invalide.");
      return;
    }
    setLoading(true);
    try {
      const response = await api.post(
        "/auth/account-reactivation/action",
        { token, action },
        { skipAuthRedirect: true }
      );
      const data = response.data;
      setDone(true);
      setStatus(data.status || (data.success ? "success" : "error"));
      setCanResend(Boolean(data.can_resend) || data.status === "expired");
      setMessage(data.message || "Action terminée.");
      if (data.success && data.redirect_to) {
        navigate(data.redirect_to, {
          replace: true,
          state: {
            reason: "account_reactivated",
            message: data.message || "Votre compte a été réactivé avec succès.",
          },
        });
      }
    } catch (err) {
      setDone(true);
      setStatus("error");
      setMessage(getApiError(err, "L’action n’a pas pu être exécutée."));
    } finally {
      setLoading(false);
    }
  }

  async function resendLink() {
    setLoading(true);
    setResendMessage("");
    try {
      const response = await api.post(
        "/auth/super-admin-reactivation/resend",
        { token },
        { skipAuthRedirect: true }
      );
      const data = response.data || {};
      setResendMessage(data.message || "Un nouveau lien a été envoyé.");
      if (data.success) {
        setCanResend(false);
      }
    } catch (err) {
      setResendMessage(getApiError(err, "Le nouveau lien n’a pas pu être envoyé."));
    } finally {
      setLoading(false);
    }
  }

  const Icon = copy?.icon || XCircle;
  const isSuccess = SUCCESS_STATUSES.has(status);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        {!done ? (
          <>
            <h1>{copy?.title || "Lien invalide"}</h1>
            <p>{copy?.description || "Ce lien de réactivation est invalide ou incomplet."}</p>
            <div className="form">
              <button
                className="btn btn-primary"
                type="button"
                onClick={executeAction}
                disabled={loading || !token || !copy}
              >
                <Icon size={18} />
                {loading ? "Exécution en cours..." : copy?.button || "Continuer"}
              </button>
              <Link className="btn btn-secondary" to="/login">
                Annuler
              </Link>
            </div>
          </>
        ) : (
          <>
            <h1>{isSuccess ? "Action confirmée" : "Action impossible"}</h1>
            <div className={isSuccess ? "alert alert-success" : "alert alert-error"}>
              {message}
            </div>
            {resendMessage && <div className="alert alert-info">{resendMessage}</div>}
            <div className="form">
              {canResend && (
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={resendLink}
                  disabled={loading || !token}
                >
                  {loading ? "Envoi en cours..." : "Renvoyer un nouveau lien"}
                </button>
              )}
              <Link className="btn btn-primary" to="/login">
                Retour à la connexion
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

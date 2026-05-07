import { CheckCircle2, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

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
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const action = useMemo(() => String(searchParams.get("action") || "").toLowerCase(), [searchParams]);
  const copy = COPY[action];

  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");

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
      setMessage(data.message || "Action terminée.");
    } catch (err) {
      setDone(true);
      setStatus("error");
      setMessage(getApiError(err, "L’action n’a pas pu être exécutée."));
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
            <div className="form">
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

import { AlertTriangle, KeyRound, ShieldOff } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

const ACTION_COPY = {
  disable: {
    title: "Désactiver le compte ?",
    description:
      "Cette action désactivera le compte concerné et révoquera ses sessions actives.",
    button: "Désactiver ce compte",
    icon: ShieldOff,
  },
  regenerate: {
    title: "Régénérer les codes de secours ?",
    description:
      "Les anciens codes seront invalidés et 10 nouveaux codes seront envoyés par email au compte concerné.",
    button: "Régénérer et envoyer les codes",
    icon: KeyRound,
  },
};

const SUCCESS_STATUSES = new Set(["success", "disabled", "regenerated"]);

export default function RecoverySupervisorActionPage() {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const action = useMemo(
    () => String(searchParams.get("action") || "").toLowerCase(),
    [searchParams]
  );
  const copy = ACTION_COPY[action];

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
    setMessage("");
    try {
      const response = await api.post(
        "/auth/recovery-codes/supervisor-action",
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

  const Icon = copy?.icon || AlertTriangle;
  const isSuccess = SUCCESS_STATUSES.has(status);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        {!done ? (
          <>
            <h1>{copy?.title || "Lien invalide"}</h1>
            <p>
              {copy?.description ||
                "Ce lien d’action est invalide ou incomplet."}
            </p>

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

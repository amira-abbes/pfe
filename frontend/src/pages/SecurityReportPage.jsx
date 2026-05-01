import { AlertTriangle, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

export default function SecurityReportPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);

  const [status, setStatus] = useState("checking");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;

    async function loadReportStatus() {
      if (!token) {
        setStatus("invalid");
        setMessage("Ce lien de signalement est invalide.");
        return;
      }

      try {
        const response = await api.post(
          "/auth/security/admin-report/status",
          { report_token: token },
          { skipAuthRedirect: true }
        );
        if (!alive) return;
        const data = response.data;
        setStatus(data.status || "invalid");
        setMessage(data.message || "");
      } catch (err) {
        if (!alive) return;
        setStatus("error");
        setMessage(getApiError(err, "État du signalement indisponible."));
      }
    }

    loadReportStatus();
    return () => {
      alive = false;
    };
  }, [token]);

  async function confirmReport() {
    setLoading(true);
    setStatus("submitting");
    setMessage("");

    try {
      const response = await api.post(
        "/auth/security/admin-report",
        { report_token: token },
        { skipAuthRedirect: true }
      );
      const data = response.data;

      if (data.force_relogin) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("current_user");
        sessionStorage.clear();
      }

      setStatus(data.status || (data.success ? "success" : "error"));
      setMessage(data.message || "Signalement enregistré. Vos sessions actives ont été révoquées.");
    } catch (err) {
      setStatus("error");
      setMessage(getApiError(err, "Le signalement n’a pas pu être confirmé."));
    } finally {
      setLoading(false);
    }
  }

  const pending = status === "pending_confirmation" || status === "submitting";
  const success = status === "success" || status === "security_report_confirmed";
  const alreadyReported = status === "already_reported";
  const expired = status === "expired" || status === "token_expired";
  const invalid = status === "invalid" || status === "invalid_or_expired_token";

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        {status === "checking" ? (
          <>
            <h1>Vérification du lien</h1>
            <div className="alert alert-info">Validation du signalement en cours.</div>
          </>
        ) : pending ? (
          <>
            <h1>Signaler une activité suspecte</h1>
            <p>
              Vous êtes sur le point de signaler une tentative de connexion
              suspecte sur votre compte.
            </p>
            <p>
              Cette action révoquera vos sessions actives par mesure de sécurité.
            </p>

            <div className="form" style={{ marginTop: 24 }}>
              <button
                className="btn btn-danger"
                type="button"
                onClick={confirmReport}
                disabled={loading || !token}
              >
                <AlertTriangle size={18} />
                {loading ? "Confirmation en cours" : "Confirmer le signalement"}
              </button>

              <button
                className="btn btn-secondary"
                type="button"
                onClick={() => navigate("/login")}
              >
                Annuler
              </button>
            </div>
          </>
        ) : success ? (
          <>
            <h1>Signalement enregistré</h1>
            <div className="alert alert-info">
              Votre signalement a été pris en compte. Par précaution, vos sessions actives ont été révoquées.
            </div>
            <button className="btn btn-primary" type="button" onClick={() => navigate("/login")}>
              <ShieldCheck size={18} />
              Retour à la connexion
            </button>
          </>
        ) : alreadyReported ? (
          <>
            <h1>Signalement déjà enregistré</h1>
            <div className="alert alert-info">Aucune action supplémentaire n’est nécessaire.</div>
            <div className="auth-links">
              <Link to="/login">Retour à la connexion</Link>
            </div>
          </>
        ) : expired ? (
          <>
            <h1>Lien de signalement expiré</h1>
            <div className="alert alert-error">
              Ce lien de signalement n’est plus valide. Veuillez vous reconnecter .
            </div>
            <div className="auth-links">
              <Link to="/login">Retour à la connexion</Link>
            </div>
          </>
        ) : invalid ? (
          <>
            <h1>Lien invalide</h1>
            <div className="alert alert-error">Ce lien de signalement est invalide.</div>
            <div className="auth-links">
              <Link to="/login">Retour à la connexion</Link>
            </div>
          </>
        ) : (
          <>
            <h1>Signalement non confirmé</h1>
            <div className="alert alert-error">{message}</div>
            <div className="auth-links">
              <Link to="/login">Retour à la connexion</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

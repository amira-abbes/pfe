import { ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

const COPY = {
  success: {
    title: "Nouveaux codes de secours envoyés",
    message:
      "De nouveaux codes de secours ont été générés et envoyés à votre adresse email. Les anciens codes ne sont plus valides.",
  },
  already_used: {
    title: "Lien déjà utilisé",
    message: "Ce lien a déjà été utilisé. Les codes de secours ont déjà été régénérés.",
  },
  expired: {
    title: "Lien expiré",
    message: "Ce lien n’est plus valide. Veuillez recommencer la procédure de récupération.",
  },
  invalid: {
    title: "Lien invalide",
    message: "Ce lien est invalide.",
  },
};

export default function RecoveryCodesRegenerateLinkPage() {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Vérification du lien en cours.");

  useEffect(() => {
    let alive = true;

    async function run() {
      if (!token) {
        setStatus("invalid");
        setMessage(COPY.invalid.message);
        return;
      }

      try {
        const response = await api.post(
          "/auth/recovery-codes/regenerate-link",
          { token },
          { skipAuthRedirect: true }
        );
        if (!alive) return;
        const data = response.data;
        setStatus(data.status || "invalid");
        setMessage(data.message || COPY.invalid.message);
      } catch (err) {
        if (!alive) return;
        setStatus("invalid");
        setMessage(getApiError(err, COPY.invalid.message));
      }
    }

    run();
    return () => {
      alive = false;
    };
  }, [token]);

  const copy = COPY[status] || {
    title: "Vérification du lien",
    message,
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>{status === "loading" ? "Vérification du lien" : copy.title}</h1>

        <div className={status === "success" || status === "already_used" ? "alert alert-info" : "alert alert-error"}>
          {status === "loading" ? message : copy.message}
        </div>

        {status === "success" && (
          <div className="alert alert-info">
            Les codes ne sont pas affichés sur cette page. Vérifiez votre boîte mail.
          </div>
        )}

        <div className="form">
          <Link className="btn btn-primary" to="/login">
            <ShieldCheck size={18} />
            Retour à la connexion
          </Link>
        </div>
      </div>
    </div>
  );
}

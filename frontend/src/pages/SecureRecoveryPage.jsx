import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";

export default function SecureRecoveryPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Vérification du lien sécurisé.");

  useEffect(() => {
    const token = searchParams.get("token") || "";
    if (!token) {
      setStatus("error");
      setMessage("Ce lien sécurisé est invalide.");
      return;
    }

    api
      .post(
        "/auth/secure-recovery/complete",
        { token },
        { skipAuthRedirect: true }
      )
      .then(async (response) => {
        const data = response.data;
        if (!data.success) {
          setStatus("error");
          setMessage(data.message || "Ce lien sécurisé n’est plus valide.");
          return;
        }

        const destination = await completeLogin(data);
        setStatus("success");
        setMessage("Connexion sécurisée validée. Votre accès est rétabli.");
        window.setTimeout(() => navigate(destination, { replace: true }), 900);
      })
      .catch((error) => {
        setStatus("error");
        setMessage(getApiError(error, "Validation du lien sécurisé impossible."));
      });
  }, [completeLogin, navigate, searchParams]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>{status === "success" ? "Connexion sécurisée validée" : "Connexion sécurisée"}</h1>
        <div className={status === "error" ? "alert alert-error" : "alert alert-info"}>
          {message}
        </div>
        {status === "error" && (
          <button className="btn btn-primary" type="button" onClick={() => navigate("/login")}>
            <ShieldCheck size={18} />
            Retour à la connexion
          </button>
        )}
      </div>
    </div>
  );
}

import { ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

function formatSeconds(totalSeconds) {
  const safe = Math.max(0, Number(totalSeconds) || 0);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(
    safe % 60
  ).padStart(2, "0")}`;
}

export default function MfaBlockedPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [remainingSeconds, setRemainingSeconds] = useState(
    Number(location.state?.remaining_seconds) || 900
  );

  const message =
    location.state?.message ||
    "Vous avez saisi plusieurs codes de vérification incorrects. Veuillez vérifier votre boîte mail pour continuer avec un code de secours ou réinitialiser votre MFA.";

  useEffect(() => {
    if (remainingSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setRemainingSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [remainingSeconds]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <h1>Vérification MFA bloquée</h1>

        <div className="alert alert-error">
          <ShieldAlert size={18} />
          {message}
        </div>

        <p>
          Vous avez saisi plusieurs codes de vérification incorrects. Veuillez
          vérifier votre boîte mail pour continuer avec un code de secours ou
          réinitialiser votre MFA.
        </p>

        <div className="alert alert-info">
          Temps restant : {formatSeconds(remainingSeconds)}
        </div>

        <button className="btn btn-primary" type="button" onClick={() => navigate("/login")}>
          Retour à la connexion
        </button>
      </div>
    </div>
  );
}

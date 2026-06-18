import { AlertTriangle, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { formatRemainingTime, parseRemainingTime } from "../utils/time";

export default function PasswordErrorPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const message = location.state?.message || "Identifiants incorrects.";
  const code = location.state?.code || "LOGIN_ERROR";
  const status = location.state?.status || "";
  const tempsRestantInitial = location.state?.temps_restant || null;
  const remainingFromState = Number(location.state?.remaining_seconds) || 0;

  const initialSeconds = useMemo(
    () => remainingFromState || parseRemainingTime(tempsRestantInitial),
    [remainingFromState, tempsRestantInitial]
  );

  const [remainingSeconds, setRemainingSeconds] = useState(initialSeconds);

  const isPasswordLockout = status === "password_lockout";
  const isAccountLocked =
    isPasswordLockout || code === "ACCOUNT_TEMPORARILY_LOCKED";
  const isDelayOnly =
    !isAccountLocked &&
    (code === "LOGIN_DELAY_REQUIRED" ||
      code === "MFA_DELAY_REQUIRED" ||
      code === "MFA_TEMPORARILY_LOCKED" ||
      initialSeconds > 0);
  const canRetry = !isDelayOnly || remainingSeconds <= 0;

  useEffect(() => {
    if (!isDelayOnly || remainingSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setRemainingSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [isDelayOnly, remainingSeconds]);

  function handleRetry() {
    if (!canRetry) return;
    navigate("/login");
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>
          {isPasswordLockout
            ? "Connexion refusée"
            : isAccountLocked
              ? "Compte bloqué"
              : "Connexion refusée"}
        </h1>

        {isAccountLocked ? (
          <div className="blocked-box">
            <div className="blocked-icon">
              <AlertTriangle size={34} />
            </div>

            <h2>Connexion refusée</h2>

            <p>
              Plusieurs tentatives de connexion incorrectes ont été détectées.
              Vous ne pouvez plus vous connecter directement. Veuillez vérifier
              votre boîte mail et suivre les instructions de sécurité.
            </p>
          </div>
        ) : (
          <div className="alert alert-error" style={{ marginTop: "22px" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <AlertTriangle size={20} style={{ marginTop: 2, flexShrink: 0 }} />
              <div>
                <strong>{message}</strong>
              </div>
            </div>
          </div>
        )}

        <div className="form" style={{ marginTop: "28px" }}>
          {isAccountLocked ? (
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => navigate("/login")}
            >
              Retour à la connexion
            </button>
          ) : (
            <>
              <button
                className={canRetry ? "btn btn-primary" : "btn btn-secondary"}
                type="button"
                onClick={handleRetry}
                disabled={!canRetry}
                style={{
                  opacity: canRetry ? 1 : 0.65,
                  cursor: canRetry ? "pointer" : "not-allowed",
                }}
              >
                <RotateCcw size={18} />
                {canRetry
                  ? "Réessayer"
                  : `Réessayer dans ${formatRemainingTime(remainingSeconds)}`}
              </button>

              <Link className="btn btn-secondary" to="/forgot-password">
                Mot de passe oublié
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

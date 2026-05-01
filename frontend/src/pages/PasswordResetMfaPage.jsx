import { KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";

function formatCountdown(seconds) {
  const safeSeconds = Math.max(0, Number(seconds || 0));
  const minutes = String(Math.floor(safeSeconds / 60)).padStart(2, "0");
  const rest = String(safeSeconds % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

export default function PasswordResetMfaPage() {
  const navigate = useNavigate();

  const initialMode = sessionStorage.getItem("reset_mfa_mode") || "totp";
  const resetMfaToken = sessionStorage.getItem("reset_mfa_token");
  const email = sessionStorage.getItem("reset_email");

  const [mode, setMode] = useState(initialMode);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [recoveryRequired, setRecoveryRequired] = useState(
    initialMode === "recovery"
  );

  useEffect(() => {
    if (cooldown <= 0) return;

    const timer = window.setInterval(() => {
      setCooldown((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [cooldown]);

  function switchToRecovery() {
    setMode("recovery");
    setCode("");
    setError("");
    setInfo("Saisissez un code de secours pour continuer la récupération.");
    sessionStorage.setItem("reset_mfa_mode", "recovery");
  }

  function handleBackendStatus(data) {
    const status = data.status;

    if (status === "success" || data.success) {
      sessionStorage.setItem("reset_password_token", data.reset_password_token);
      navigate("/password-reset/complete");
      return;
    }

    if (status === "cooldown") {
      const remaining = Number(data.remaining_seconds || data.cooldown_seconds || 30);
      setCooldown(remaining);
      setError(data.message || "Plusieurs erreurs MFA. Veuillez réessayer plus tard.");
      return;
    }

    if (status === "recovery_required") {
      setRecoveryRequired(true);
      setMode("blocked");
      setCode("");
      setError("");
      setInfo(
        data.message ||
          "Vérification MFA bloquée temporairement. Un email de sécurité vous a été envoyé."
      );
      return;
    }

    setError(data.message || "Code incorrect. Veuillez réessayer.");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (cooldown > 0 || mode === "blocked") return;

    setError("");
    setInfo("");
    setLoading(true);

    try {
      if (!resetMfaToken) {
        navigate("/forgot-password");
        return;
      }

      const endpoint =
        mode === "recovery"
          ? "/auth/password-reset/recovery-code/verify"
          : "/auth/password-reset/totp/verify";

      const payload =
        mode === "recovery"
          ? { reset_mfa_token: resetMfaToken, code_secours: code }
          : { reset_mfa_token: resetMfaToken, code };

      const response = await api.post(endpoint, payload);
      handleBackendStatus(response.data);
    } catch (err) {
      setError(getApiError(err, "Erreur de vérification MFA."));
    } finally {
      setLoading(false);
    }
  }

  const isCooldown = cooldown > 0;
  const isRecovery = mode === "recovery";
  const isBlocked = mode === "blocked";

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Vérification sécurité</h1>

        {!isBlocked && (
          <p>
            {isRecovery
              ? "Entrez un code de secours."
              : "Entrez le code Authenticator."}
          </p>
        )}

        {email && <div className="alert alert-info">Compte : {email}</div>}
        {info && <div className="alert alert-info">{info}</div>}
        {error && (
          <div className={isCooldown ? "alert alert-info" : "alert alert-error"}>
            {error}
            {isCooldown && (
              <>
                <br />
                Temps restant : {formatCountdown(cooldown)}
              </>
            )}
          </div>
        )}

        {isBlocked && (
          <div className="blocked-box">
            <h2>Vérification MFA bloquée temporairement</h2>
            <p>Un email de sécurité vous a été envoyé.</p>
            <button className="btn btn-primary" onClick={switchToRecovery}>
              <KeyRound size={18} />
              Réinitialiser avec un code de secours
            </button>
          </div>
        )}

        {!isBlocked && (
          <form className="form" onSubmit={handleSubmit}>
            <div className="input-group">
              <label>{isRecovery ? "Code de secours" : "Code TOTP"}</label>
              <input
                className="input"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                disabled={loading || isCooldown}
                required
              />
            </div>

            <button className="btn btn-primary" disabled={loading || isCooldown}>
              <ShieldCheck size={18} />
              {loading ? "Vérification..." : "Valider"}
            </button>

            {!isRecovery && (recoveryRequired || !isCooldown) && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={switchToRecovery}
              >
                <KeyRound size={18} />
                Réinitialiser avec un code de secours
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}

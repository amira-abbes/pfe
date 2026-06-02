import { ArrowRight, KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import AuthTriangles from "../components/AuthTriangles";
import OtpInput from "../components/OtpInput";

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
    if (cooldown <= 0) return undefined;

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
      <AuthTriangles />

      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Vérification sécurité</h1>
        <div className="rainbow-line" />

        {!isBlocked && (
          <p className="subtitle" style={{ textAlign: "center", marginBottom: "24px" }}>
            {isRecovery
              ? "Entrez l'un de vos codes de secours à 10 chiffres."
              : "Entrez le code à 6 chiffres de votre application Authenticator."}
          </p>
        )}

        {email && !error && !info && (
          <div style={{ textAlign: "center", marginBottom: "20px", fontSize: "13px", color: "#64748b" }}>
            Compte : <strong>{email}</strong>
          </div>
        )}

        {info && <div className="auth-error-banner" style={{ background: "#f8fafc", color: "#64748b", border: "1px solid #e2e8f0" }}>{info}</div>}
        {error && (
          <div className="auth-error-banner">
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
          <div className="blocked-box" style={{ textAlign: "center" }}>
            <button className="btn-primary" onClick={switchToRecovery} style={{ width: "100%" }}>
              <KeyRound size={18} />
              Utiliser un code de secours
            </button>
          </div>
        )}

        {!isBlocked && (
          <form className="form" onSubmit={handleSubmit}>
            <div className="input-group">
              {isRecovery ? (
                <div className="input-icon-wrap">
                  <span className="input-icon-left"><KeyRound size={17} /></span>
                  <input
                    className="input"
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    placeholder="Code à 10 chiffres"
                    disabled={loading || isCooldown}
                    required
                  />
                </div>
              ) : (
                <>
                  <label className="otp-label">
                    <ShieldCheck size={17} />
                    Code Authenticator
                  </label>
                  <OtpInput
                    value={code}
                    onChange={setCode}
                    autoFocus
                    disabled={loading || isCooldown}
                    ariaLabel="Code Authenticator"
                  />
                </>
              )}
            </div>

            <button className="btn-primary" disabled={loading || isCooldown}>
              {loading ? "Vérification..." : "Valider"}
              {!loading && <ArrowRight size={18} />}
            </button>

            {!isRecovery && (recoveryRequired || !isCooldown) && (
              <div className="auth-forgot" style={{ textAlign: "center", marginTop: "16px", justifyContent: "center" }}>
                <button
                  type="button"
                  onClick={switchToRecovery}
                  style={{ background: "none", border: "none", padding: 0, cursor: "pointer", display: "flex", alignItems: "center", gap: "8px" }}
                >
                  <KeyRound size={15} /> Utiliser un code de secours
                </button>
              </div>
            )}
          </form>
        )}

        <div className="auth-forgot" style={{ textAlign: "center", marginTop: "24px", justifyContent: "center" }}>
          <Link to="/login">Retour à la connexion</Link>
        </div>
      </div>
    </div>
  );
}

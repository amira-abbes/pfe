import { KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";
import AuthTriangles from "../components/AuthTriangles";
import { formatRemainingTime } from "../utils/time";

const RECOVERY_CODE_LENGTH = 10;

export default function RecoveryCodePage() {
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const codeInputRef = useRef(null);

  const [codeSecours, setCodeSecours] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  const mfaToken = sessionStorage.getItem("mfa_token");
  const isCodeComplete = codeSecours.length === RECOVERY_CODE_LENGTH;

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  function updateCode(value) {
    setCodeSecours(value.slice(0, RECOVERY_CODE_LENGTH));
    setError("");
  }

  function handlePaste(event) {
    event.preventDefault();
    const input = event.currentTarget;
    const start = input.selectionStart ?? codeSecours.length;
    const end = input.selectionEnd ?? start;
    const pasted = event.clipboardData.getData("text");
    updateCode(
      `${codeSecours.slice(0, start)}${pasted}${codeSecours.slice(end)}`
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (!isCodeComplete) {
      setError("Le code de secours doit contenir exactement 10 caractères.");
      window.setTimeout(() => codeInputRef.current?.focus(), 0);
      return;
    }

    setLoading(true);

    try {
      if (!mfaToken) {
        setError(
          "Session de vérification introuvable. Veuillez recommencer la connexion."
        );
        return;
      }

      const response = await api.post(
        "/auth/recovery-code/verify",
        {
          mfa_token: mfaToken,
          recovery_code: codeSecours,
        },
        { skipAuthRedirect: true }
      );

      const data = response.data;

      if (!data.success) {
        setCodeSecours("");
        window.setTimeout(() => codeInputRef.current?.focus(), 0);
        setCooldownSeconds(Number(data.remaining_seconds) || 0);
        setError(data.message || "Code de secours invalide ou déjà utilisé.");

        if (
          data.status === "mfa_session_expired" ||
          data.status === "missing_mfa_token"
        ) {
          sessionStorage.removeItem("mfa_token");
        }

        if (data.status === "recovery_code_direct_blocked") {
          window.setTimeout(
            () => navigate(data.redirect_to || "/auth/totp", { replace: true }),
            1200
          );
        }

        return;
      }

      const destination = await completeLogin(data);
      navigate(destination, { replace: true });
    } catch (err) {
      setCodeSecours("");
      window.setTimeout(() => codeInputRef.current?.focus(), 0);
      setError(
        getApiError(
          err,
          "Connexion validée, mais le chargement de votre session a échoué."
        )
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <AuthTriangles />

      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Code de secours</h1>
        <div className="rainbow-line" />

        <p
          className="subtitle"
          style={{ textAlign: "center", marginBottom: "24px" }}
        >
          Utilisez l'un de vos codes de secours à 10 caractères pour accéder à
          votre compte.
        </p>

        {error && <div className="auth-error-banner">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left">
                <KeyRound size={17} />
              </span>
              <input
                ref={codeInputRef}
                className="input"
                value={codeSecours}
                onChange={(event) => updateCode(event.target.value)}
                onPaste={handlePaste}
                placeholder="Code à 10 caractères"
                maxLength={RECOVERY_CODE_LENGTH}
                autoCapitalize="characters"
                autoCorrect="off"
                spellCheck={false}
                required
                disabled={cooldownSeconds > 0}
              />
            </div>
            <div
              style={{
                marginTop: "8px",
                textAlign: "center",
                color: "#64748b",
                fontSize: "12.5px",
              }}
            >
              Le code de secours doit contenir exactement 10 caractères.
            </div>
          </div>

          <button
            className="btn-primary"
            type="submit"
            disabled={loading || cooldownSeconds > 0 || !isCodeComplete}
          >
            {loading
              ? "Vérification..."
              : cooldownSeconds > 0
                ? `Réessayer (${formatRemainingTime(cooldownSeconds)})`
                : "Valider le code"}
          </button>
        </form>

        <div
          className="auth-forgot"
          style={{ textAlign: "center", marginTop: "24px" }}
        >
          <Link
            to="/auth/totp"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
            }}
          >
            <ShieldCheck size={15} /> Retour à l'Authenticator
          </Link>
        </div>
      </div>
    </div>
  );
}

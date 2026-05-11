import { KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";
import AuthTriangles from "../components/AuthTriangles";

export default function RecoveryCodePage() {
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const codeInputRef = useRef(null);

  const [codeSecours, setCodeSecours] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  const mfaToken = sessionStorage.getItem("mfa_token");

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (!mfaToken) {
        setError("Session de vérification introuvable. Veuillez recommencer la connexion.");
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

        if (data.status === "mfa_session_expired" || data.status === "missing_mfa_token") {
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
      setError(getApiError(err, "Connexion validée, mais le chargement de votre session a échoué."));
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

        <p className="subtitle" style={{ textAlign: 'center', marginBottom: '24px' }}>
          Utilisez l'un de vos codes de secours à 10 chiffres pour accéder à votre compte.
        </p>

        {error && <div className="auth-error-banner">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><KeyRound size={17} /></span>
              <input
                ref={codeInputRef}
                className="input"
                value={codeSecours}
                onChange={(event) => setCodeSecours(event.target.value)}
                placeholder="Code à 10 chiffres"
                required
                disabled={cooldownSeconds > 0}
              />
            </div>
          </div>

          <button
            className="btn-primary"
            type="submit"
            disabled={loading || cooldownSeconds > 0}
          >
            {loading
              ? "Vérification..."
              : cooldownSeconds > 0
                ? `Réessayer (${cooldownSeconds}s)`
                : "Valider le code"}
          </button>
        </form>

        <div className="auth-forgot" style={{ textAlign: 'center', marginTop: '24px' }}>
          <Link to="/auth/totp" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <ShieldCheck size={15} /> Retour à l'Authenticator
          </Link>
        </div>
      </div>
    </div>
  );
}

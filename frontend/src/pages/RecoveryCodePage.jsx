import { ArrowRight, KeyRound, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";
import "../styles/auth_redesign.css";

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
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <div className="auth-tagline">La vie est émotions</div>

        <h1>Code secours</h1>
        <div className="rainbow-underline"></div>

        <p style={{ marginBottom: '24px', textAlign: 'left', color: '#64748b', fontSize: '14px' }}>
          Utilisez un code de secours non encore utilisé pour vous connecter.
        </p>

        {error && <div className="alert-error">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Lock size={18} /></span>
              <input
                ref={codeInputRef}
                className="input"
                value={codeSecours}
                onChange={(event) => setCodeSecours(event.target.value)}
                placeholder="Ex : 8K2M7P4Q9A"
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
                ? `Attente ${cooldownSeconds}s`
                : "Valider le code"}
            {!loading && cooldownSeconds <= 0 && (
              <div className="btn-arrow-circle">
                <ArrowRight size={18} />
              </div>
            )}
          </button>
        </form>

        <div className="auth-links" style={{ marginTop: '24px' }}>
          <Link to="/auth/totp" style={{ textDecoration: 'none', color: '#2563eb', fontWeight: 600, fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <KeyRound size={16} /> Retour Authenticator
          </Link>
        </div>
      </div>
    </div>
  );
}

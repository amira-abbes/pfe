import { ArrowRight, KeyRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";
import "../styles/auth_redesign.css";

export default function TotpPage() {
  const navigate = useNavigate();
  const { completeLogin, isAuthenticated, loading: authLoading } = useAuth();
  const codeInputRef = useRef(null);

  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [loading, setLoading] = useState(false);

  const email = sessionStorage.getItem("mfa_email");
  const mfaToken = sessionStorage.getItem("mfa_token");

  useEffect(() => {
    if (!mfaToken && !isAuthenticated && !authLoading) {
      navigate("/login", { replace: true });
    }
  }, [mfaToken, isAuthenticated, authLoading, navigate]);

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  function handleCodeChange(value) {
    const clean = value.replace(/\D/g, "").slice(0, 6);
    setCode(clean);
  }

  function clearCodeAfterError(shouldFocus = true) {
    setCode("");

    if (shouldFocus) {
      window.setTimeout(() => codeInputRef.current?.focus(), 0);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);

    try {
      if (!mfaToken) {
        navigate("/login", { replace: true });
        return;
      }

      if (code.length !== 6) {
        setError("Le code doit contenir 6 chiffres.");
        clearCodeAfterError();
        return;
      }

      const response = await api.post(
        "/auth/totp/verify",
        {
          mfa_token: mfaToken,
          code,
        },
        { skipAuthRedirect: true }
      );

      const data = response.data || {};

      if (
        data.status === "recovery_required" ||
        data.reason === "mfa_blocked" ||
        data.code === "MFA_BLOCKED"
      ) {
        navigate(data.redirect_to || "/mfa-blocked", {
          replace: true,
          state: {
            message: data.message,
            remaining_seconds: data.remaining_seconds || data.expires_in_seconds,
            mail_sent: data.mail_sent,
          },
        });
        return;
      }

      if (data.status === "cooldown") {
        const seconds = Number(data.remaining_seconds) || 60;
        setCooldownSeconds(seconds);
        setError(
          data.message ||
            `Plusieurs codes incorrects. Veuillez patienter ${seconds} secondes.`
        );
        clearCodeAfterError(false);
        return;
      }

      if (data.status === "invalid_format" || data.status === "invalid_code") {
        setError(data.message || "Code incorrect. Veuillez réessayer.");
        clearCodeAfterError();
        return;
      }

      if (data.code === "MFA_TOKEN_INVALID") {
        sessionStorage.removeItem("mfa_token");
        sessionStorage.removeItem("mfa_email");
        sessionStorage.removeItem("mfa_role");
        sessionStorage.removeItem("mfa_setup_token");
        navigate("/login", { replace: true });
        return;
      }

      if (data.success === false) {
        setError(data.message || "Vérification refusée.");
        clearCodeAfterError();
        return;
      }

      if (!data.access_token) {
        setError(data.message || "Vérification refusée.");
        clearCodeAfterError();
        return;
      }

      const destination = await completeLogin(data);

      sessionStorage.removeItem("mfa_token");
      sessionStorage.removeItem("mfa_email");
      sessionStorage.removeItem("mfa_role");
      sessionStorage.removeItem("mfa_setup_token");

      navigate(destination, { replace: true });
    } catch (err) {
      clearCodeAfterError();
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
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
        <div className="auth-tagline">La vie est émotions</div>

        <h1>Vérification</h1>
        <div className="rainbow-underline"></div>

        <p style={{ marginBottom: '24px', textAlign: 'left', color: '#64748b', fontSize: '14px' }}>
          Entrez le code à 6 chiffres généré par votre application Authenticator.
        </p>

        {error && <div className="alert-error">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <input
              ref={codeInputRef}
              className="mfa-code-input"
              value={code}
              onChange={(event) => handleCodeChange(event.target.value)}
              placeholder="000000"
              inputMode="numeric"
              maxLength={6}
              autoFocus
              required
              disabled={cooldownSeconds > 0 || loading}
            />
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
                : "Vérifier"}
            {!loading && cooldownSeconds <= 0 && (
              <div className="btn-arrow-circle">
                <ArrowRight size={18} />
              </div>
            )}
          </button>
        </form>

        <div className="auth-links" style={{ marginTop: '24px' }}>
          <Link to="/auth/recovery-code" style={{ textDecoration: 'none', color: '#2563eb', fontWeight: 600, fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <KeyRound size={16} /> Utiliser un code de secours
          </Link>
        </div>
      </div>
    </div>
  );
}
import { KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";
import AuthTriangles from "../components/AuthTriangles";
import OtpInput from "../components/OtpInput";
import { formatRemainingTime } from "../utils/time";

const MFA_TOTP_COOLDOWN_KEY = "mfa_totp_cooldown";
const MAX_STORED_COOLDOWN_MS = 15 * 60 * 1000;

function clearStoredCooldown() {
  sessionStorage.removeItem(MFA_TOTP_COOLDOWN_KEY);
}

function readStoredCooldown(mfaToken) {
  if (!mfaToken) {
    clearStoredCooldown();
    return 0;
  }

  try {
    const stored = JSON.parse(sessionStorage.getItem(MFA_TOTP_COOLDOWN_KEY));
    const remainingMs = Number(stored?.endsAt) - Date.now();

    if (
      stored?.mfaToken !== mfaToken ||
      !Number.isFinite(remainingMs) ||
      remainingMs <= 0 ||
      remainingMs > MAX_STORED_COOLDOWN_MS
    ) {
      clearStoredCooldown();
      return 0;
    }

    return Number(stored.endsAt);
  } catch {
    clearStoredCooldown();
    return 0;
  }
}

export default function TotpPage() {
  const navigate = useNavigate();
  const { completeLogin, isAuthenticated, loading: authLoading } = useAuth();
  const email = sessionStorage.getItem("mfa_email");
  const mfaToken = sessionStorage.getItem("mfa_token");

  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [cooldownUntil, setCooldownUntil] = useState(() =>
    readStoredCooldown(mfaToken)
  );
  const [cooldownSeconds, setCooldownSeconds] = useState(() =>
    Math.max(0, Math.ceil((readStoredCooldown(mfaToken) - Date.now()) / 1000))
  );
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!mfaToken && !isAuthenticated && !authLoading) {
      clearStoredCooldown();
      navigate("/login", { replace: true });
    }
  }, [mfaToken, isAuthenticated, authLoading, navigate]);

  useEffect(() => {
    if (cooldownUntil <= 0) return undefined;

    const updateCountdown = () => {
      const seconds = Math.max(
        0,
        Math.ceil((cooldownUntil - Date.now()) / 1000)
      );
      setCooldownSeconds(seconds);

      if (seconds === 0) {
        clearStoredCooldown();
        setCooldownUntil(0);
      }
    };

    const timer = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownUntil]);

  function startCooldown(secondsValue) {
    const seconds = Math.max(1, Number(secondsValue) || 60);
    const endsAt = Date.now() + seconds * 1000;

    sessionStorage.setItem(
      MFA_TOTP_COOLDOWN_KEY,
      JSON.stringify({ mfaToken, endsAt })
    );
    setCooldownUntil(endsAt);
    setCooldownSeconds(seconds);
    setCode("");
    setError("");
    setInfo("");
  }

  function handleCodeChange(value) {
    if (cooldownUntil > Date.now()) return;
    const clean = value.replace(/\D/g, "").slice(0, 6);
    setCode(clean);
  }

  function clearCodeAfterError() {
    setCode("");
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (cooldownUntil > Date.now()) {
      setCooldownSeconds(
        Math.max(1, Math.ceil((cooldownUntil - Date.now()) / 1000))
      );
      return;
    }

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

      if (data.status === "account_blocked" || data.reason === "account_blocked") {
        clearStoredCooldown();
        navigate(data.redirect_to || "/account-disabled", {
          replace: true,
          state: {
            email: data.email || email,
            role: data.role || "SUPER_ADMIN",
            message: data.message,
            reason: "account_blocked",
            can_request_reactivation: data.can_request_reactivation,
          },
        });
        return;
      }

      if (
        data.status === "recovery_required" ||
        data.reason === "mfa_blocked" ||
        data.code === "MFA_BLOCKED"
      ) {
        clearStoredCooldown();
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

      if (data.status === "secure_link_required") {
        setError(
          data.message ||
          "Connexion restreinte. Vous pouvez seulement vous connecter à partir du lien sécurisé envoyé dans votre boîte mail."
        );
        setCode("");
        return;
      }

      if (
        data.status === "cooldown" ||
        data.reason === "mfa_cooldown_active" ||
        data.reason === "mfa_cooldown_60s" ||
        data.code === "MFA_DELAY_REQUIRED" ||
        data.code === "TOTP_TEMPORARILY_LOCKED"
      ) {
        startCooldown(data.remaining_seconds || data.expires_in_seconds);
        return;
      }

      if (data.status === "invalid_format" || data.status === "invalid_code") {
        setError(data.message || "Code incorrect. Veuillez réessayer.");
        clearCodeAfterError();
        return;
      }

      if (data.code === "MFA_TOKEN_INVALID") {
        clearStoredCooldown();
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

      clearStoredCooldown();
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
      <AuthTriangles />
      
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Authenticator</h1>
        <div className="rainbow-line" />

        <p className="subtitle" style={{ textAlign: 'center', marginBottom: '24px' }}>
          Entrez le code à 6 chiffres généré par votre application Authenticator.
        </p>

        {email && !error && !info && (
          <div style={{ textAlign: 'center', marginBottom: '20px', fontSize: '13px', color: '#64748b' }}>
            Compte : <strong>{email}</strong>
          </div>
        )}
        
        {cooldownSeconds > 0 && (
          <div className="auth-error-banner">
            Trop de tentatives incorrectes. Veuillez réessayer dans{" "}
            {formatRemainingTime(cooldownSeconds)}.
          </div>
        )}
        {info && cooldownSeconds <= 0 && <div className="auth-error-banner" style={{ background: '#f8fafc', color: '#64748b', border: '1px solid #e2e8f0' }}>{info}</div>}
        {error && <div className="auth-error-banner">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="otp-label">
              <ShieldCheck size={17} />
              Code de vérification
            </div>
            <OtpInput
              value={code}
              onChange={handleCodeChange}
              autoFocus
              disabled={cooldownSeconds > 0 || loading}
              ariaLabel="Code Authenticator"
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
                ? `Réessayer (${formatRemainingTime(cooldownSeconds)})`
                : "Vérifier"}
          </button>
        </form>

        <div className="auth-forgot" style={{ textAlign: 'center', marginTop: '24px' }}>
          <Link to="/auth/recovery-code" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <KeyRound size={15} /> Utiliser un code de secours
          </Link>
        </div>
      </div>
    </div>
  );
}

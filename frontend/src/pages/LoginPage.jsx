import { ArrowRight, Eye, EyeOff, Lock, Mail } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";
import AuthTriangles from "../components/AuthTriangles";
import { formatRemainingTime } from "../utils/time";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { completeLogin } = useAuth();
  const passwordInputRef = useRef(null);

  const [form, setForm] = useState({ email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [showPassword, setShowPassword] = useState(false);

  const loginReason = location.state?.reason || searchParams.get("reason");
  const infoMessage =
    location.state?.message ||
    (loginReason === "auth_required" ? "Veuillez vous reconnecter." : "");

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function clearPasswordAfterError() {
    setForm((current) => ({ ...current, password: "" }));
    window.setTimeout(() => passwordInputRef.current?.focus(), 0);
  }

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;
    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  async function handleSubmit(event, overrideEmail = null, overridePassword = null) {
    if (event) event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await api.post("/auth/login", {
        email: overrideEmail || form.email,
        password: overridePassword || form.password,
      });

      const data = response.data;

      if (!data.success) {
        clearPasswordAfterError();

        if (data.status === "mfa_setup_required") {
          sessionStorage.setItem("mfa_setup_token", data.setup_token || "");
          sessionStorage.setItem("mfa_role", data.role || "USER");
          navigate("/mfa/setup");
          return;
        }

        if (data.status === "activation_totp_setup_required") {
          sessionStorage.setItem("totp_setup_token", data.setup_token || "");
          sessionStorage.setItem("activation_email", data.email || form.email);
          navigate(data.redirect_to || "/activation/totp");
          return;
        }

        if (data.status === "recovery_required" || data.reason === "mfa_blocked") {
          navigate(data.redirect_to || "/mfa-blocked", {
            state: {
              message: data.message,
              remaining_seconds: data.remaining_seconds,
              mail_sent: data.mail_sent,
            },
          });
          return;
        }

        if (data.status === "invalid_credentials") {
          setError(data.message || "Identifiants incorrects.");
          return;
        }

        if (
          [
            "account_disabled",
            "account_blocked",
            "account_pending_first_login",
            "account_deleted",
          ].includes(data.status)
        ) {
          navigate(data.redirect_to || "/account-disabled", {
            state: {
              email: data.email || form.email,
              role: data.role || "USER",
              message: data.message,
              reason: data.status,
              can_request_reactivation: data.can_request_reactivation,
            },
          });
          return;
        }

        if (data.status === "password_cooldown") {
          setCooldownSeconds(Number(data.remaining_seconds) || 30);
          setError(data.message || "Veuillez patienter avant de réessayer.");
          return;
        }

        if (data.status === "password_lockout") {
          navigate("/password-error", {
            state: {
              code: data.code,
              message: data.message,
              temps_restant: data.temps_restant,
              status: data.status,
              remaining_seconds: data.remaining_seconds,
            },
          });
          return;
        }

        if (data.status === "mail_verification_required") {
          navigate("/mail-verification-required", {
            state: {
              message: data.message,
              mail_sent: data.mail_sent,
              email_expires_in_seconds: data.email_expires_in_seconds,
            },
          });
          return;
        }

        if (data.status === "secure_link_required") {
          setError(
            data.message ||
            "Connexion impossible. Veuillez vérifier votre boîte mail."
          );
          return;
        }

        setError(data.message || "Connexion refusée.");
        return;
      }

      if (data.code === "MFA_REQUIRED") {
        sessionStorage.setItem("mfa_token", data.mfa_token);
        sessionStorage.setItem("mfa_email", data.email || form.email);
        sessionStorage.setItem("mfa_role", data.role || "USER");
        navigate("/auth/totp");
        return;
      }

      if (data.access_token) {
        await completeLogin(data);
        navigate("/accueil", { replace: true });
      }
    } catch (err) {
      clearPasswordAfterError();
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

        <h1>Se connecter</h1>
        <div className="rainbow-line" />

        {infoMessage && <div className="auth-info-banner" style={{ background: "rgba(37, 99, 235, 0.15)", border: "1px solid rgba(37, 99, 235, 0.4)", color: "#93c5fd", padding: "10px 14px", borderRadius: "12px", marginBottom: "18px", fontSize: "13px", fontWeight: 600 }}>{infoMessage}</div>}
        {error && <div className="auth-error-banner">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          {/* Email */}
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Mail size={17} /></span>
              <input
                className="input"
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={(e) => updateField("email", e.target.value)}
                placeholder="Adresse e-mail"
                required
              />
            </div>
          </div>

          {/* Password */}
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Lock size={17} /></span>
              <input
                ref={passwordInputRef}
                className="input has-right-icon"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={form.password}
                onChange={(e) => updateField("password", e.target.value)}
                placeholder="Mot de passe"
                required
              />
              <button
                type="button"
                className="input-icon-right"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </div>

          {/* Forgot password */}
          <div className="auth-forgot">
            <Link to="/forgot-password">Mot de passe oublié ?</Link>
          </div>

          {/* Submit */}
          <button
            className="btn-primary"
            type="submit"
            disabled={loading || cooldownSeconds > 0}
          >
            {loading
              ? "Connexion..."
              : cooldownSeconds > 0
                ? `Réessayer (${formatRemainingTime(cooldownSeconds)})`
                : "Se connecter"}
            {!loading && cooldownSeconds <= 0 && <ArrowRight size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
}



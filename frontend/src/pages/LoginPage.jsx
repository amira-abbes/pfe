import { KeyRound, LogIn } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { completeLogin } = useAuth();
  const passwordInputRef = useRef(null);

  const [form, setForm] = useState({
    email: "",
    password: "",
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const loginReason = location.state?.reason || searchParams.get("reason");
  const infoMessage =
    loginReason === "session_expired"
      ? "Votre session a expiré après 30 minutes d’inactivité. Veuillez vous reconnecter."
      : loginReason === "auth_required"
        ? "Veuillez vous reconnecter."
        : "";

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

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await api.post("/auth/login", {
        email: form.email,
        password: form.password,
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
              "Connexion impossible. Veuillez vérifier votre boîte mail. Le lien sécurisé reçu par email est l’unique moyen de connexion pendant cette période."
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
        const destination = await completeLogin(data);
        navigate(destination, { replace: true });
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
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Connexion</h1>
        <p>Accédez à la plateforme interne Tunisie Telecom.</p>

        {infoMessage && <div className="alert alert-info">{infoMessage}</div>}
        {error && <div className="alert alert-error">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <label>Email</label>
            <input
              className="input"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={(event) => updateField("email", event.target.value)}
              placeholder="email@exemple.com"
              required
            />
          </div>

          <div className="input-group">
            <label>Mot de passe</label>
            <input
              ref={passwordInputRef}
              className="input"
              type="password"
              autoComplete="current-password"
              value={form.password}
              onChange={(event) => updateField("password", event.target.value)}
              placeholder="Votre mot de passe"
              required
            />
          </div>

          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading || cooldownSeconds > 0}
          >
            <LogIn size={18} />
            {loading
              ? "Connexion en cours"
              : cooldownSeconds > 0
                ? `Réessayer dans ${cooldownSeconds}s`
                : "Se connecter"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/forgot-password">
            <KeyRound size={15} /> Mot de passe oublié
          </Link>
        </div>
      </div>
    </div>
  );
}

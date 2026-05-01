import { KeyRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";

const ROLE_COPY = {
  SUPER_ADMIN: {
    intro:
      "Saisissez un code de secours pour confirmer votre identité et accéder à votre compte super administrateur.",
    help:
      "Vos codes de secours vous ont été fournis lors de l’activation de votre compte. Vérifiez votre boîte mail ou vos téléchargements. Si vous n’avez plus accès à ces codes, utilisez l’option de réinitialisation MFA ou le lien sécurisé reçu par email.",
  },
  ADMIN: {
    intro:
      "Saisissez un code de secours pour confirmer votre identité et accéder à votre compte administrateur.",
    help:
      "Vos codes de secours vous ont été fournis lors de l’activation de votre compte. Vérifiez votre boîte mail ou vos téléchargements. Si vous n’avez plus accès à ces codes, contactez le super administrateur.",
  },
  USER: {
    intro:
      "Saisissez un code de secours pour confirmer votre identité et accéder à votre compte.",
    help:
      "Vos codes de secours vous ont été fournis lors de l’activation de votre compte. Vérifiez votre boîte mail ou vos téléchargements. Si vous n’avez plus accès à ces codes, contactez l’administrateur de votre département.",
  },
  GENERIC: {
    intro:
      "Saisissez un code de secours pour confirmer votre identité et accéder à votre compte.",
    help:
      "Vos codes de secours vous ont été fournis lors de l’activation de votre compte. Vérifiez votre boîte mail ou vos téléchargements.",
  },
};

export default function MfaRecoveryCodeLinkPage() {
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const codeInputRef = useRef(null);
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const role = useMemo(() => {
    const value = String(searchParams.get("role") || "").toUpperCase();
    return ROLE_COPY[value] ? value : "GENERIC";
  }, [searchParams]);
  const copy = ROLE_COPY[role];

  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;
    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    setError("");

    const cleanCode = code.trim().replace(/\s/g, "").toUpperCase();
    if (cleanCode.length > 30 || cleanCode.length < 6) {
      setError("Format du code de secours invalide.");
      return;
    }

    setLoading(true);
    try {
      const response = await api.post(
        "/auth/mfa/recovery-code/verify-link",
        { token, code_secours: cleanCode },
        { skipAuthRedirect: true }
      );
      const data = response.data;

      if (!data.success) {
        setError(data.message || "Code de secours invalide ou déjà utilisé.");
        setCooldownSeconds(Number(data.remaining_seconds) || 0);
        setCode("");
        if (!data.remaining_seconds) window.setTimeout(() => codeInputRef.current?.focus(), 0);
        return;
      }

      const destination = await completeLogin(data);
      navigate(destination, { replace: true });
    } catch (err) {
      setCode("");
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
        <h1>Utiliser un code de secours</h1>
        <p>{copy.intro}</p>
        <p>{copy.help}</p>

        {message && <div className="alert alert-info">{message}</div>}
        {error && <div className="alert alert-error">{error}</div>}
        {cooldownSeconds > 0 && (
          <div className="alert alert-info">
            Temps restant : {String(Math.floor(cooldownSeconds / 60)).padStart(2, "0")}:
            {String(cooldownSeconds % 60).padStart(2, "0")}
          </div>
        )}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <label>Code de secours</label>
            <input
              ref={codeInputRef}
              className="input"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="XXXX-XXXX"
              disabled={cooldownSeconds > 0}
              autoFocus
              required
            />
          </div>

          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading || cooldownSeconds > 0 || !token}
          >
            <KeyRound size={18} />
            {loading ? "Vérification en cours" : "Vérifier le code"}
          </button>
        </form>
      </div>
    </div>
  );
}

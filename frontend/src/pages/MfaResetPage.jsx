import { KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

function formatSeconds(totalSeconds) {
  const safe = Math.max(0, Number(totalSeconds) || 0);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(
    safe % 60
  ).padStart(2, "0")}`;
}

export default function MfaResetPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const recoveryInputRef = useRef(null);
  const totpInputRef = useRef(null);

  const [step, setStep] = useState("recovery");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [qrCodeBase64, setQrCodeBase64] = useState("");
  const [otpauthUri, setOtpauthUri] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [totpCooldownSeconds, setTotpCooldownSeconds] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  useEffect(() => {
    if (totpCooldownSeconds <= 0) return undefined;

    const timer = window.setInterval(() => {
      setTotpCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [totpCooldownSeconds]);

  function clearRecoveryField(shouldFocus = true) {
    setRecoveryCode("");
    if (shouldFocus) window.setTimeout(() => recoveryInputRef.current?.focus(), 0);
  }

  function clearTotpField() {
    setTotpCode("");
    window.setTimeout(() => totpInputRef.current?.focus(), 0);
  }

  async function verifyRecoveryCode(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const response = await api.post(
        "/auth/mfa/reset/recovery-code/verify",
        { token, recovery_code: recoveryCode },
        { skipAuthRedirect: true }
      );
      const data = response.data;

      if (!data.success) {
        setError(data.message || "Code de secours invalide ou déjà utilisé.");
        setCooldownSeconds(Number(data.remaining_seconds) || 0);
        clearRecoveryField(!data.remaining_seconds);
        return;
      }

      setQrCodeBase64(data.qr_code_base64 || "");
      setOtpauthUri(data.otpauth_uri || "");
      setStep("qr");
      setMessage("Code de secours valide. Scannez le nouveau QR code.");
    } catch (err) {
      setError(getApiError(err, "Vérification impossible."));
      clearRecoveryField();
    } finally {
      setLoading(false);
    }
  }

  async function confirmNewMfa(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const response = await api.post(
        "/auth/mfa/reset/confirm",
        { token, code: totpCode },
        { skipAuthRedirect: true }
      );
      const data = response.data;

      if (!data.success) {
        setError(data.message || "Code incorrect. Veuillez réessayer.");
        setTotpCooldownSeconds(Number(data.remaining_seconds) || 0);
        if (data.status === "mfa_reset_failed") {
          setStep("failed");
        }
        clearTotpField();
        return;
      }

      setStep("success");
      setMessage(data.message || "Votre MFA a été réinitialisée avec succès.");
    } catch (err) {
      setError(getApiError(err, "Activation impossible."));
      clearTotpField();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        {step === "recovery" && (
          <>
            <h1>Réinitialisation MFA</h1>
            <p>
              Pour réinitialiser votre application Authenticator, saisissez
              d'abord un code de secours.
            </p>
            <p>
              Vos codes de secours vous ont été fournis lors de l'activation de
              votre compte. Vérifiez votre boîte mail ou vos téléchargements.
              Si vous n'avez plus accès à ces codes, utilisez le lien sécurisé
              reçu par email ou contactez votre administrateur.
            </p>

            {error && <div className="alert alert-error">{error}</div>}
            {cooldownSeconds > 0 && (
              <div className="alert alert-info">
                Réessayer dans {formatSeconds(cooldownSeconds)}
              </div>
            )}

            <form className="form" onSubmit={verifyRecoveryCode}>
              <div className="input-group">
                <label>Code de secours</label>
                <input
                  ref={recoveryInputRef}
                  className="input"
                  value={recoveryCode}
                  onChange={(event) => setRecoveryCode(event.target.value)}
                  disabled={cooldownSeconds > 0}
                  required
                  autoFocus
                />
              </div>

              <button
                className="btn btn-primary"
                type="submit"
                disabled={loading || cooldownSeconds > 0 || !token}
              >
                <KeyRound size={18} />
                {loading ? "Vérification en cours" : "Continuer"}
              </button>
            </form>
          </>
        )}

        {step === "qr" && (
          <>
            <h1>Scanner le nouveau QR code</h1>
            <p>
              Ouvrez Google Authenticator ou Microsoft Authenticator, puis
              scannez ce QR code.
            </p>

            {message && <div className="alert alert-info">{message}</div>}
            {error && <div className="alert alert-error">{error}</div>}
            {totpCooldownSeconds > 0 && (
              <div className="alert alert-info">
                Réessayer dans {formatSeconds(totpCooldownSeconds)}
              </div>
            )}
            {qrCodeBase64 ? (
              <img
                src={`data:image/png;base64,${qrCodeBase64}`}
                alt="QR code MFA"
                style={{ width: 220, height: 220, margin: "16px auto", display: "block" }}
              />
            ) : (
              <div className="alert alert-info">{otpauthUri}</div>
            )}

            <form className="form" onSubmit={confirmNewMfa}>
              <div className="input-group">
                <label>Code généré par la nouvelle application</label>
                <input
                  ref={totpInputRef}
                  className="input"
                  value={totpCode}
                  onChange={(event) =>
                    setTotpCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  inputMode="numeric"
                  maxLength={6}
                  disabled={totpCooldownSeconds > 0}
                  required
                  autoFocus
                />
              </div>

              <button
                className="btn btn-primary"
                type="submit"
                disabled={loading || totpCooldownSeconds > 0}
              >
                <ShieldCheck size={18} />
                {loading ? "Activation en cours" : "Activer la nouvelle MFA"}
              </button>
            </form>
          </>
        )}

        {step === "success" && (
          <>
            <h1>MFA réinitialisée avec succès</h1>
            <div className="alert alert-info">{message}</div>
            <button className="btn btn-primary" type="button" onClick={() => navigate("/login")}>
              Retour à la connexion
            </button>
          </>
        )}

        {step === "failed" && (
          <>
            <h1>Réinitialisation MFA interrompue</h1>
            <p>
              Plusieurs codes incorrects ont été saisis pendant la configuration
              de votre nouvelle MFA. Pour protéger votre compte, cette opération
              a été interrompue.
            </p>
            {error && <div className="alert alert-error">{error}</div>}
            <button className="btn btn-primary" type="button" onClick={() => navigate("/login")}>
              Retour à la connexion
            </button>
          </>
        )}

        <div className="auth-links">
          <Link to="/login">Retour à la connexion</Link>
        </div>
      </div>
    </div>
  );
}

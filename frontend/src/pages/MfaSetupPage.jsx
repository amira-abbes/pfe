import { Download, QrCode, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import { useAuth } from "../context/AuthContext";

function downloadCodes(codes) {
  const content = [
    "Codes de secours - Tunisie Telecom Platform",
    "",
    "Chaque code est utilisable une seule fois.",
    "",
    ...codes.map((code) => `- ${code}`),
  ].join("\n");
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "codes-secours.txt";
  link.click();
  URL.revokeObjectURL(url);
}

export default function MfaSetupPage() {
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const codeInputRef = useRef(null);

  const setupToken = sessionStorage.getItem("mfa_setup_token") || "";
  const [step, setStep] = useState("intro");
  const [qrCode, setQrCode] = useState("");
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [destination, setDestination] = useState("/user/dashboard");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  useEffect(() => {
    if (cooldownSeconds <= 0) return undefined;
    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  async function startSetup() {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await api.post(
        "/auth/mfa/setup/start",
        { setup_token: setupToken },
        { skipAuthRedirect: true }
      );
      const data = response.data;
      if (!data.success) {
        setError(data.message || "Configuration MFA impossible.");
        return;
      }
      setQrCode(data.qr_code_base64 || data.qr_code || "");
      setMessage(data.message || "Scannez le QR code avec votre application Authenticator.");
      setStep("qr");
      window.setTimeout(() => codeInputRef.current?.focus(), 0);
    } catch (err) {
      setError(getApiError(err, "Configuration MFA impossible."));
    } finally {
      setLoading(false);
    }
  }

  async function confirmSetup(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await api.post(
        "/auth/mfa/setup/confirm",
        { setup_token: setupToken, code },
        { skipAuthRedirect: true }
      );
      const data = response.data;
      if (!data.success) {
        setCode("");
        setCooldownSeconds(Number(data.remaining_seconds) || 0);
        if (data.status === "setup_cancelled" || data.status === "token_expired") {
          sessionStorage.removeItem("mfa_setup_token");
          setStep("cancelled");
          return;
        }
        setError(data.message || "Code incorrect. Veuillez réessayer.");
        window.setTimeout(() => codeInputRef.current?.focus(), 0);
        return;
      }

      const nextDestination = await completeLogin(data);
      setDestination(nextDestination);
      setRecoveryCodes(data.recovery_codes || []);
      setMessage(data.message || "MFA configurée avec succès.");
      setStep("codes");
    } catch (err) {
      setCode("");
      setError(getApiError(err, "Connexion validée, mais le chargement de votre session a échoué."));
      window.setTimeout(() => codeInputRef.current?.focus(), 0);
    } finally {
      setLoading(false);
    }
  }

  function finish() {
    navigate(destination, { replace: true });
  }

  return (
    <div className="auth-page">
      <div className="auth-card recovery-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        {step === "intro" && (
          <>
            <h1>Configurer la vérification MFA</h1>
            <p>
              Pour protéger votre compte, vous devez configurer une application
              Authenticator.
            </p>
            {error && <div className="alert alert-error">{error}</div>}
            <button className="btn btn-primary" onClick={startSetup} disabled={loading || !setupToken}>
              <QrCode size={18} />
              {loading ? "Génération..." : "Générer le QR code"}
            </button>
          </>
        )}

        {step === "qr" && (
          <>
            <h1>Scanner le QR code</h1>
            <p>Scannez ce QR code avec Google Authenticator ou Microsoft Authenticator.</p>
            {message && <div className="alert alert-info">{message}</div>}
            {error && <div className="alert alert-error">{error}</div>}
            {cooldownSeconds > 0 && (
              <div className="alert alert-info">Réessayer dans {cooldownSeconds}s</div>
            )}
            {qrCode && (
              <img
                className="qr-img"
                src={`data:image/png;base64,${qrCode}`}
                alt="QR code Authenticator"
              />
            )}
            <form className="form" onSubmit={confirmSetup}>
              <div className="input-group">
                <label>Code Authenticator</label>
                <input
                  ref={codeInputRef}
                  className="input"
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  inputMode="numeric"
                  maxLength={6}
                  disabled={cooldownSeconds > 0}
                  required
                />
              </div>
              <button className="btn btn-primary" disabled={loading || cooldownSeconds > 0}>
                <ShieldCheck size={18} />
                {loading ? "Validation en cours" : "Confirmer la MFA"}
              </button>
            </form>
          </>
        )}

        {step === "codes" && (
          <>
            <h1>MFA configurée avec succès</h1>
            <div className="alert alert-info">
              Conservez ces codes de secours. Ils ne seront plus affichés après cette étape.
            </div>
            <div className="code-list">
              {recoveryCodes.map((item) => (
                <div className="code-item" key={item}>
                  {item}
                </div>
              ))}
            </div>
            <button className="btn btn-secondary" onClick={() => downloadCodes(recoveryCodes)}>
              <Download size={18} />
              Télécharger les codes
            </button>
            <button className="btn btn-primary" onClick={finish}>
              Accéder au dashboard
            </button>
          </>
        )}

        {step === "cancelled" && (
          <>
            <h1>Configuration interrompue</h1>
            <div className="alert alert-error">
              Trop de codes incorrects. Veuillez recommencer la connexion.
            </div>
            <button className="btn btn-primary" onClick={() => navigate("/login")}>
              Retour à la connexion
            </button>
          </>
        )}
      </div>
    </div>
  );
}

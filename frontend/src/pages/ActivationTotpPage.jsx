import { Download, Mail, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getApiError } from "../api/api";
import OtpInput from "../components/OtpInput";

export default function ActivationTotpPage() {
  const navigate = useNavigate();

  const setupToken = sessionStorage.getItem("totp_setup_token");
  const setupStartedRef = useRef(false);

  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [codesSaved, setCodesSaved] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function start() {
      try {
        if (setupStartedRef.current) {
          return;
        }
        setupStartedRef.current = true;

        if (!setupToken) {
          navigate("/login");
          return;
        }

        const response = await api.post("/auth/activation/totp/setup/start", {
          totp_setup_token: setupToken,
        });

        setSetup(response.data);
      } catch (err) {
        setError(getApiError(err, "Erreur génération Authenticator."));
      }
    }

    start();
  }, [setupToken, navigate]);

  function downloadCodes() {
    setError("");

    if (downloaded) {
      return;
    }

    if (!recoveryCodes.length) {
      setError("Aucun code de secours disponible à télécharger.");
      return;
    }

    const content = [
      "Codes de secours - Tunisie Telecom",
      "",
      "Ces codes servent si vous perdez l’accès à votre application Authenticator.",
      "Chaque code est utilisable une seule fois.",
      "",
      ...recoveryCodes.map((item) => `- ${item}`),
    ].join("\n");

    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = "codes-secours-tunisie-telecom.txt";
    link.click();

    URL.revokeObjectURL(url);
    setDownloaded(true);
    setCodesSaved(true);
    setMessage("Les codes ont été téléchargés.");
  }

  async function sendCodesEmail() {
    setError("");

    if (emailSent) {
      setMessage("Les codes ont déjà été envoyés par email.");
      return;
    }

    setEmailSending(true);
    try {
      const response = await api.post("/auth/activation/recovery-codes/email", {
        totp_setup_token: setupToken,
        recovery_codes: recoveryCodes,
      });

      if (!response.data.success) {
        setError(response.data.message);
        return;
      }

      setEmailSent(true);
      setCodesSaved(true);
      setMessage(response.data.message);
    } catch (err) {
      setError(getApiError(err, "Erreur envoi codes par email."));
    } finally {
      setEmailSending(false);
    }
  }

  async function handleVerify(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      if (code.length !== 6) {
        setError("Veuillez saisir le code Authenticator à 6 chiffres.");
        return;
      }

      const response = await api.post("/auth/activation/totp/setup/verify", {
        totp_setup_token: setupToken,
        code,
      });

      const data = response.data;

      if (!data.success) {
        setError(
          `${data.message}${data.temps_restant ? ` Temps restant : ${data.temps_restant}` : ""}`
        );
        return;
      }

      setMessage(data.message);
      setRecoveryCodes(data.recovery_codes || []);
    } catch (err) {
      setError(getApiError(err, "Erreur validation Authenticator."));
    } finally {
      setLoading(false);
    }
  }

  function continueToLogin() {
    if (!codesSaved) {
      setError("Veuillez télécharger vos codes ou les recevoir par email avant de continuer.");
      return;
    }

    sessionStorage.removeItem("totp_setup_token");
    sessionStorage.removeItem("activation_email");
    navigate("/login");
  }

  return (
    <div className="auth-page">
      <div className="auth-card recovery-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        {!recoveryCodes.length && (
          <>
            <h1>Configurer Authenticator</h1>
            <p>
              Scannez le QR code avec Google Authenticator ou Microsoft Authenticator.
            </p>

            {error && <div className="alert alert-error">{error}</div>}

            {setup?.qr_code_base64 && (
              <img
                className="qr-img"
                src={`data:image/png;base64,${setup.qr_code_base64}`}
                alt="QR Code Authenticator"
              />
            )}

            {setup?.secret && (
              <div className="alert alert-info">
                Clé secrète : <strong>{setup.secret}</strong>
              </div>
            )}

            <form className="form" onSubmit={handleVerify}>
              <div className="input-group">
                <label className="otp-label">Code Authenticator</label>
                <OtpInput
                  value={code}
                  onChange={setCode}
                  autoFocus
                  disabled={loading}
                  ariaLabel="Code Authenticator"
                />
              </div>

              <button className="btn btn-primary" disabled={loading}>
                <ShieldCheck size={18} />
                {loading ? "Vérification en cours" : "Activer mon compte"}
              </button>
            </form>
          </>
        )}

        {recoveryCodes.length > 0 && (
          <>
            <h1>Sauvegarder vos codes</h1>

            {error && <div className="alert alert-error">{error}</div>}
            {message && <div className="alert alert-success">{message}</div>}

            <div className="alert alert-info">
              Ces codes servent si vous perdez l’accès à votre application Authenticator.
              Chaque code est utilisable une seule fois. Ils ne seront plus affichés après cette étape.
            </div>

            <div className="code-list">
              {recoveryCodes.map((item) => (
                <div className="code-item" key={item}>
                  {item}
                </div>
              ))}
            </div>

            <div className="actions" style={{ marginTop: 18 }}>
              <button
                className="btn btn-secondary"
                onClick={downloadCodes}
                disabled={downloaded}
              >
                <Download size={18} />
                {downloaded ? "Déjà téléchargé" : "Télécharger mes codes"}
              </button>

              <button
                className="btn btn-secondary"
                onClick={sendCodesEmail}
                disabled={emailSending || emailSent}
              >
                <Mail size={18} />
                {emailSent ? "Déjà envoyé" : emailSending ? "Envoi en cours" : "Recevoir par email"}
              </button>
            </div>

            <div className="form">
              <button className="btn btn-primary" onClick={continueToLogin}>
                J’ai sauvegardé mes codes, continuer
              </button>

              <Link className="btn btn-secondary" to="/login">
                Retour login
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

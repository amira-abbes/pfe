import {
  CheckCircle2,
  Download,
  Eye,
  EyeOff,
  FileDigit,
  Info,
  KeyRound,
  LockKeyhole,
  Mail,
  RefreshCcw,
  ShieldCheck,
  Smartphone,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import OtpInput from "../components/OtpInput";

export default function AccountSecurityPage() {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ mot_de_passe: "", code_totp: "" });
  const [newCodes, setNewCodes] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);

  async function loadStatus() {
    try {
      const response = await api.get("/auth/security/recovery-codes/status");
      setStatus(response.data);
    } catch (err) {
      setError(getApiError(err, "Erreur chargement sécurité."));
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (!regenerateOpen) return undefined;
    document.body.classList.add("modal-open");
    return () => document.body.classList.remove("modal-open");
  }, [regenerateOpen]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function closeRegenerateModal() {
    setRegenerateOpen(false);
    setShowPassword(false);
    setForm({ mot_de_passe: "", code_totp: "" });
  }

  function openRegenerateModal() {
    setError("");
    setMessage("");
    setRegenerateOpen(true);
  }

  function downloadCodes(codes = newCodes) {
    if (!codes.length) return;
    const content = [
      "Codes de secours - Tunisie Telecom",
      "",
      "Ces codes servent si vous perdez l’accès à votre application Authenticator.",
      "Chaque code est utilisable une seule fois.",
      "",
      ...codes.map((code) => `- ${code}`),
    ].join("\n");
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "codes-secours-tunisie-telecom.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function sendCodesEmail(codes = newCodes) {
    setError("");
    setMessage("");
    try {
      const response = await api.post("/auth/security/recovery-codes/email", { recovery_codes: codes });
      setMessage(response.data.message);
    } catch (err) {
      setError(getApiError(err, "Erreur envoi email."));
    }
  }

  async function regenerate(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setNewCodes([]);
    if (form.code_totp.length !== 6) {
      setError("Le code Authenticator doit contenir 6 chiffres.");
      return;
    }
    try {
      const response = await api.post("/auth/security/recovery-codes/regenerate", {
        mot_de_passe: form.mot_de_passe,
        code_totp: form.code_totp,
      });
      setNewCodes(response.data.recovery_codes || []);
      setMessage(response.data.message);
      setForm({ mot_de_passe: "", code_totp: "" });
      await loadStatus();
    } catch (err) {
      setError(getApiError(err, "Erreur régénération codes."));
    }
  }

  const kpis = [
    { label: "Total", value: status?.total_codes ?? "-", icon: FileDigit, tone: "blue" },
    { label: "Restants", value: status?.codes_restants ?? "-", icon: CheckCircle2, tone: "cyan" },
    { label: "Utilisés", value: status?.codes_utilises ?? "-", icon: XCircle, tone: "violet" },
  ];
  const remainingRecoveryCodes = Number(status?.codes_restants ?? 0);
  const hasRemainingRecoveryCodes = remainingRecoveryCodes > 0;
  const canRegenerateRecoveryCodes = status !== null && remainingRecoveryCodes === 0;

  return (
    <Layout>
      <div className="security-workspace">
        <section className="security-hero">
          <div className="security-hero-icon"><LockKeyhole size={34} /></div>
          <div className="security-hero-copy">
            <span className="security-eyebrow">Protection du compte</span>
            <h1>Sécurité</h1>
            <p>Protégez votre accès à la plateforme grâce à l’authentification multifacteur et aux codes de secours.</p>
          </div>
          <div className="security-hero-status"><i /><span>MFA activée</span><small>Authenticator TOTP</small></div>
        </section>

        {(error || message) && <div className={`security-feedback ${error ? "error" : "success"}`}>{error || message}</div>}

        <div className="security-compact-alert">
          <Info size={17} />
          <span>Chaque code de secours est utilisable une seule fois et remplace temporairement votre application Authenticator.</span>
        </div>

        <section className="security-kpi-grid">
          {kpis.map(({ label, value, icon: Icon, tone }) => (
            <article className={`security-kpi ${tone}`} key={label}>
              <span><Icon size={20} /></span>
              <div><strong>{value}</strong><small>{label}</small></div>
            </article>
          ))}
        </section>

        {status?.codes_restants === 0 && (
          <div className="security-feedback error">Aucun code de secours disponible. Régénérez une nouvelle liste après confirmation.</div>
        )}

        <section className="security-columns">
          <article className="security-panel">
            <div className="security-panel-head">
              <span><ShieldCheck size={21} /></span>
              <div><small>Authentification</small><h2>Authentification MFA</h2></div>
            </div>
            <div className="security-mfa-highlight">
              <span><Smartphone size={22} /></span>
              <div><strong>Protection active</strong><small>Une vérification supplémentaire est demandée lors de la connexion.</small></div>
              <b><i />Activée</b>
            </div>
            <dl className="security-detail-list">
              <div><dt>Statut</dt><dd>Configurée</dd></div>
              <div><dt>Méthode</dt><dd>Application Authenticator</dd></div>
              <div><dt>Protocole</dt><dd>TOTP</dd></div>
            </dl>
            <button className="security-secondary-button" type="button" disabled><ShieldCheck size={16} />MFA configurée</button>
          </article>

          <article className="security-panel">
            <div className="security-panel-head">
              <span><KeyRound size={21} /></span>
              <div><small>Accès de secours</small><h2>Codes de secours</h2></div>
            </div>
            <div className="security-code-summary">
              <div><strong>{status?.codes_restants ?? "-"}</strong><small>codes disponibles</small></div>
              <span>{status?.total_codes ? Math.round(((status.codes_restants || 0) / status.total_codes) * 100) : 0}%</span>
            </div>
            <dl className="security-detail-list">
              <div><dt>Dernière génération</dt><dd>Non disponible</dd></div>
              <div><dt>Codes utilisés</dt><dd>{status?.codes_utilises ?? "-"}</dd></div>
              <div><dt>Usage</dt><dd>Une seule fois par code</dd></div>
            </dl>
            <div className="security-panel-actions">
              <button
                className="security-primary-button"
                type="button"
                onClick={openRegenerateModal}
                disabled={!canRegenerateRecoveryCodes}
                title={hasRemainingRecoveryCodes ? "Tous les codes doivent être utilisés avant de pouvoir générer une nouvelle liste." : undefined}
                aria-describedby={hasRemainingRecoveryCodes ? "recovery-codes-regeneration-help" : undefined}
              >
                <RefreshCcw size={16} />Régénérer
              </button>
              {newCodes.length > 0 && <button className="security-secondary-button" type="button" onClick={() => downloadCodes()}><Download size={16} />Télécharger</button>}
              {newCodes.length > 0 && <button className="security-secondary-button" type="button" onClick={() => sendCodesEmail()}><Mail size={16} />Email</button>}
            </div>
            {hasRemainingRecoveryCodes && (
              <p className="security-regeneration-help" id="recovery-codes-regeneration-help">
                Vous disposez encore de codes de secours valides. La régénération sera disponible une fois tous les codes utilisés.
              </p>
            )}
          </article>
        </section>
      </div>

      {regenerateOpen && createPortal(
        <div className="security-modal-overlay" role="presentation" onMouseDown={closeRegenerateModal}>
          <section className="security-modal" role="dialog" aria-modal="true" aria-label="Régénérer les codes de secours" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span>Confirmation sécurisée</span><h2>Régénérer les codes de secours</h2><p>Cette action invalide définitivement tous les anciens codes.</p></div>
              <button type="button" onClick={closeRegenerateModal} aria-label="Fermer"><X size={18} /></button>
            </header>
            <div className="security-modal-body">
              {(error || message) && <div className={`security-feedback ${error ? "error" : "success"}`}>{error || message}</div>}
              {newCodes.length > 0 ? (
                <>
                  <div className="security-compact-alert success"><CheckCircle2 size={17} /><span>Vos nouveaux codes ont été générés. Conservez-les dans un endroit sûr.</span></div>
                  <div className="code-list security-code-list">
                    {newCodes.map((code) => <div className="code-item" key={code}>{code}</div>)}
                  </div>
                </>
              ) : (
                <form id="security-regenerate-form" onSubmit={regenerate} className="security-regenerate-form">
                  <label>Mot de passe actuel
                    <div className="input-icon-wrap">
                      <input className="au-input" type={showPassword ? "text" : "password"} value={form.mot_de_passe} onChange={(event) => updateField("mot_de_passe", event.target.value)} placeholder="Votre mot de passe" required />
                      <button type="button" className="input-icon-right" onClick={() => setShowPassword((current) => !current)} tabIndex={-1}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
                    </div>
                  </label>
                  <label>Code Authenticator
                    <OtpInput value={form.code_totp} onChange={(value) => updateField("code_totp", value)} ariaLabel="Code Authenticator" />
                  </label>
                </form>
              )}
            </div>
            <footer>
              <button className="security-secondary-button" type="button" onClick={closeRegenerateModal}>Fermer</button>
              {newCodes.length > 0
                ? <button className="security-primary-button" type="button" onClick={() => downloadCodes()}><Download size={16} />Télécharger</button>
                : <button className="security-primary-button" type="submit" form="security-regenerate-form"><RefreshCcw size={16} />Régénérer les codes</button>}
            </footer>
          </section>
        </div>,
        document.body
      )}
    </Layout>
  );
}

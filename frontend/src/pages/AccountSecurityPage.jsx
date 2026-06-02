import { CheckCircle2, Download, Eye, EyeOff, FileDigit, Info, Mail, RefreshCcw, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import OtpInput from "../components/OtpInput";

export default function AccountSecurityPage() {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({
    mot_de_passe: "",
    code_totp: "",
  });
  const [newCodes, setNewCodes] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

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

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
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
      const response = await api.post("/auth/security/recovery-codes/email", {
        recovery_codes: codes,
      });

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

  return (
    <Layout>
      {/* ── Page header ── */}
      <div className="au-page-header">
        <div>
          <h1 className="au-page-title">Sécurité du compte</h1>
          <p className="au-page-sub">Gestion des codes de secours et récupération MFA.</p>
        </div>
        <button
          className="au-btn-create"
          style={{ background: "#fff7ed", color: "#b54708", border: "1px solid #fedf89", boxShadow: "none" }}
        >
          <ShieldCheck size={18} />
          WebAuthn non configuré
        </button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
      {message && <div className="alert alert-success" style={{ marginBottom: 16 }}>{message}</div>}

      {/* ── Info Banner ── */}
      <div className="au-security-info-banner">
        <Info size={24} style={{ color: "#2563eb", flexShrink: 0, marginTop: "2px" }} />
        <div style={{ color: "#175cd3", fontSize: "14px", lineHeight: "1.6" }}>
          <strong style={{ display: "block", marginBottom: "4px", fontSize: "15px" }}>À quoi servent ces codes ?</strong>
          Les codes de secours permettent de se connecter si vous perdez l’accès à Google Authenticator ou Microsoft Authenticator.<br/>
          Chaque code est utilisable une seule fois. Après utilisation des 10 codes, vous devez régénérer une nouvelle liste.
        </div>
      </div>

      {/* ── Stats cards ── */}
      {status && (
        <div className="au-stats-row">
          <div className="au-stat-card">
            <div className="au-stat-icon" style={{ background: "#eff6ff", color: "#2563eb" }}>
              <FileDigit size={26} />
            </div>
            <div>
              <div className="au-stat-value">{status.total_codes}</div>
              <div className="au-stat-label">Total</div>
            </div>
          </div>
          <div className="au-stat-card">
            <div className="au-stat-icon" style={{ background: "#f0fdf4", color: "#10b981" }}>
              <CheckCircle2 size={26} />
            </div>
            <div>
              <div className="au-stat-value" style={{ color: "#10b981" }}>{status.codes_restants}</div>
              <div className="au-stat-label">Restants</div>
            </div>
          </div>
          <div className="au-stat-card">
            <div className="au-stat-icon" style={{ background: "#fef2f2", color: "#ef4444" }}>
              <XCircle size={26} />
            </div>
            <div>
              <div className="au-stat-value" style={{ color: "#ef4444" }}>{status.codes_utilises}</div>
              <div className="au-stat-label">Utilisés</div>
            </div>
          </div>
        </div>
      )}

      {status?.codes_restants === 0 && (
        <div className="alert alert-error" style={{ marginBottom: 24 }}>
          Aucun code de secours disponible. Régénérez une nouvelle liste après confirmation.
        </div>
      )}

      {/* ── Regenerate Form ── */}
      <div className="au-table-card" style={{ padding: "24px", marginBottom: "24px" }}>
        <h2 className="au-page-title" style={{ fontSize: "18px", marginBottom: "8px" }}>Régénérer mes codes de secours</h2>
        <p style={{ color: "#64748b", fontSize: "14px", marginBottom: "24px" }}>
          Cette action invalide tous les anciens codes et génère 10 nouveaux codes.
          Une confirmation par mot de passe et Authenticator est obligatoire.
        </p>

        <form onSubmit={regenerate} className="au-security-form">
          <div className="au-field" style={{ marginBottom: "16px" }}>
            <label className="au-label">Mot de passe actuel</label>
            <div className="input-icon-wrap">
              <input
                className="au-input"
                style={{ paddingRight: "46px", width: "100%" }}
                type={showPassword ? "text" : "password"}
                value={form.mot_de_passe}
                onChange={(event) => updateField("mot_de_passe", event.target.value)}
                placeholder="Votre mot de passe"
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

          <div className="au-field" style={{ marginBottom: "16px" }}>
            <label className="au-label">Code Authenticator</label>
            <OtpInput
              value={form.code_totp}
              onChange={(value) => updateField("code_totp", value)}
              disabled={false}
              ariaLabel="Code Authenticator"
            />
          </div>

          <button className="au-btn-create" style={{ width: "100%", marginTop: "8px", justifyContent: "center" }}>
            <RefreshCcw size={18} />
            Régénérer les codes
          </button>
        </form>
      </div>

      {/* ── Generated Codes ── */}
      {newCodes.length > 0 && (
        <div className="au-table-card" style={{ padding: "24px" }}>
          <h2 className="au-page-title" style={{ fontSize: "18px", marginBottom: "16px" }}>Nouveaux codes générés</h2>

          <div className="alert alert-info" style={{ marginBottom: "16px" }}>
            Ces codes ne seront affichés qu’une seule fois. Téléchargez-les ou envoyez-les par email.
          </div>

          <div className="code-list">
            {newCodes.map((code) => (
              <div className="code-item" key={code}>
                {code}
              </div>
            ))}
          </div>

          <div className="au-security-actions">
            <button className="btn btn-secondary" onClick={() => downloadCodes()}>
              <Download size={18} />
              Télécharger
            </button>

            <button className="btn btn-secondary" onClick={() => sendCodesEmail()}>
              <Mail size={18} />
              Recevoir par email
            </button>
          </div>
        </div>
      )}
    </Layout>
  );
}

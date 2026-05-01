import { Download, Mail, RefreshCcw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";

export default function AccountSecurityPage() {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({
    mot_de_passe: "",
    code_totp: "",
  });
  const [newCodes, setNewCodes] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

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
    <Layout
      title="Sécurité du compte"
      subtitle="Gestion des codes de secours et récupération MFA."
    >
      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div className="grid grid-2">
        <div className="card">
          <h2>État des codes de secours</h2>

          {status && (
            <>
              <p>{status.message}</p>

              <div className="grid grid-3">
                <div className="mini-stat">
                  <strong>{status.total_codes}</strong>
                  <span>Total</span>
                </div>
                <div className="mini-stat">
                  <strong>{status.codes_restants}</strong>
                  <span>Restants</span>
                </div>
                <div className="mini-stat">
                  <strong>{status.codes_utilises}</strong>
                  <span>Utilisés</span>
                </div>
              </div>

              {status.codes_restants === 0 && (
                <div className="alert alert-error">
                  Aucun code de secours disponible. Régénérez une nouvelle liste après confirmation.
                </div>
              )}
            </>
          )}
        </div>

        <div className="card">
          <h2>À quoi servent ces codes ?</h2>
          <p>
            Les codes de secours permettent de se connecter si vous perdez l’accès à Google
            Authenticator ou Microsoft Authenticator.
          </p>
          <p>
            Chaque code est utilisable une seule fois. Après utilisation des 10 codes, vous devez
            régénérer une nouvelle liste.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>Régénérer mes codes de secours</h2>
        <p>
          Cette action invalide tous les anciens codes et génère 10 nouveaux codes.
          Une confirmation par mot de passe et Authenticator est obligatoire.
        </p>

        <form className="form" onSubmit={regenerate}>
          <div className="input-group">
            <label>Mot de passe actuel</label>
            <input
              className="input"
              type="password"
              value={form.mot_de_passe}
              onChange={(event) => updateField("mot_de_passe", event.target.value)}
              required
            />
          </div>

          <div className="input-group">
            <label>Code Authenticator</label>
            <input
              className="input"
              value={form.code_totp}
              onChange={(event) =>
                updateField("code_totp", event.target.value.replace(/\D/g, "").slice(0, 6))
              }
              placeholder="123456"
              maxLength={6}
              required
            />
          </div>

          <button className="btn btn-primary">
            <RefreshCcw size={18} />
            Régénérer les codes
          </button>
        </form>
      </div>

      {newCodes.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <h2>Nouveaux codes générés</h2>

          <div className="alert alert-info">
            Ces codes ne seront affichés qu’une seule fois. Téléchargez-les ou envoyez-les par email.
          </div>

          <div className="code-list">
            {newCodes.map((code) => (
              <div className="code-item" key={code}>
                {code}
              </div>
            ))}
          </div>

          <div className="actions" style={{ marginTop: 18 }}>
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
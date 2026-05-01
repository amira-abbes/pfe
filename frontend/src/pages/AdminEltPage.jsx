import { PlayCircle, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";

export default function AdminEltPage() {
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [actionToken, setActionToken] = useState("");
  const [sensitiveToken, setSensitiveToken] = useState("");
  const [loading, setLoading] = useState(false);

  async function startWebAuthn() {
    setError("");
    setMessage("");
    setActionToken("");
    setSensitiveToken("");
    setLoading(true);

    try {
      const response = await api.post("/admin/sensitive/elt/start-webauthn");
      const data = response.data;

      if (!data.success) {
        setError(data.message);
        return;
      }

      setActionToken(data.webauthn_action_token);
      setMessage("Validation action sensible demandée.");
    } catch (err) {
      setError(getApiError(err, "Erreur préparation WebAuthn."));
    } finally {
      setLoading(false);
    }
  }

  async function verifyDemo() {
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const response = await api.post("/admin/sensitive/elt/verify-webauthn-demo", {
        webauthn_action_token: actionToken,
        credential: {},
      });

      const data = response.data;

      if (!data.success) {
        setError(data.message);
        return;
      }

      setSensitiveToken(data.sensitive_action_token);
      setMessage("Action sensible confirmée. Vous pouvez lancer ELT.");
    } catch (err) {
      setError(getApiError(err, "Erreur validation action sensible."));
    } finally {
      setLoading(false);
    }
  }

  async function launchElt() {
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const response = await api.post("/admin/sensitive/elt/launch", {
        sensitive_action_token: sensitiveToken,
      });

      const data = response.data;

      if (!data.success) {
        setError(data.message);
        return;
      }

      setMessage(data.message);
      setActionToken("");
      setSensitiveToken("");
    } catch (err) {
      setError(getApiError(err, "Erreur lancement ELT."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout
      title="Traitement ELT"
      subtitle="Action sensible réservée aux administrateurs."
    >
      <div className="card">
        <h2>Lancement ELT</h2>

        <p>
          Cette action doit être validée par WebAuthn pour les administrateurs.
          Dans cette version locale, la validation démo simule la confirmation
          afin de permettre le test complet du parcours.
        </p>

        {error && <div className="alert alert-error">{error}</div>}
        {message && <div className="alert alert-success">{message}</div>}

        <div className="actions" style={{ marginTop: 18 }}>
          <button className="btn btn-primary" onClick={startWebAuthn} disabled={loading}>
            <ShieldAlert size={18} />
            Demander validation sensible
          </button>

          {actionToken && (
            <button className="btn btn-secondary" onClick={verifyDemo} disabled={loading}>
              Valider WebAuthn démo
            </button>
          )}

          {sensitiveToken && (
            <button className="btn btn-success" onClick={launchElt} disabled={loading}>
              <PlayCircle size={18} />
              Lancer ELT
            </button>
          )}
        </div>
      </div>
    </Layout>
  );
}
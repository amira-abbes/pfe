import { Save } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";

export default function PasswordResetCompletePage() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    nouveau_mot_de_passe: "",
    confirmation_mot_de_passe: "",
  });

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const resetPasswordToken = sessionStorage.getItem("reset_password_token");

      if (!resetPasswordToken) {
        navigate("/forgot-password");
        return;
      }

      const response = await api.post("/auth/password-reset/complete", {
        reset_password_token: resetPasswordToken,
        nouveau_mot_de_passe: form.nouveau_mot_de_passe,
        confirmation_mot_de_passe: form.confirmation_mot_de_passe,
      });

      setSuccess(response.data.message);

      sessionStorage.removeItem("reset_password_token");
      sessionStorage.removeItem("reset_mfa_token");
      sessionStorage.removeItem("reset_email");
      sessionStorage.removeItem("reset_mfa_mode");

      setTimeout(() => navigate("/login"), 1200);
    } catch (err) {
      setError(getApiError(err, "Erreur lors du changement de mot de passe."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Nouveau mot de passe</h1>
        <p>Choisissez un mot de passe fort et différent de l’ancien.</p>

        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <label>Nouveau mot de passe</label>
            <input
              className="input"
              type="password"
              value={form.nouveau_mot_de_passe}
              onChange={(event) =>
                updateField("nouveau_mot_de_passe", event.target.value)
              }
              required
            />
          </div>

          <div className="input-group">
            <label>Confirmation</label>
            <input
              className="input"
              type="password"
              value={form.confirmation_mot_de_passe}
              onChange={(event) =>
                updateField("confirmation_mot_de_passe", event.target.value)
              }
              required
            />
          </div>

          <button className="btn btn-primary" disabled={loading}>
            <Save size={18} />
            {loading ? "Enregistrement en cours" : "Changer le mot de passe"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Retour connexion</Link>
        </div>
      </div>
    </div>
  );
}
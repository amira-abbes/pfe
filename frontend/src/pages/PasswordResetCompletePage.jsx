import { ArrowRight, Eye, EyeOff, Lock } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import "../styles/auth_redesign.css";

export default function PasswordResetCompletePage() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    nouveau_mot_de_passe: "",
    confirmation_mot_de_passe: "",
  });

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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
        <div className="auth-tagline">La vie est émotions</div>

        <h1>Mot de passe</h1>
        <div className="rainbow-underline"></div>

        <p style={{ marginBottom: '24px', textAlign: 'left', color: '#64748b', fontSize: '14px' }}>
          Choisissez un mot de passe fort et différent de l’ancien.
        </p>

        {error && <div className="alert-error">{error}</div>}
        {success && <div className="alert-error" style={{ background: '#ecfdf3', color: '#027a48' }}>{success}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Lock size={18} /></span>
              <input
                className="input has-right-icon"
                type={showPassword ? "text" : "password"}
                value={form.nouveau_mot_de_passe}
                onChange={(event) =>
                  updateField("nouveau_mot_de_passe", event.target.value)
                }
                placeholder="Nouveau mot de passe"
                required
              />
              <button
                type="button"
                className="input-icon-right"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Lock size={18} /></span>
              <input
                className="input has-right-icon"
                type={showConfirmPassword ? "text" : "password"}
                value={form.confirmation_mot_de_passe}
                onChange={(event) =>
                  updateField("confirmation_mot_de_passe", event.target.value)
                }
                placeholder="Confirmer mot de passe"
                required
              />
              <button
                type="button"
                className="input-icon-right"
                onClick={() => setShowConfirmPassword((v) => !v)}
                tabIndex={-1}
              >
                {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? "Enregistrement..." : "Changer le mot de passe"}
            {!loading && (
              <div className="btn-arrow-circle">
                <ArrowRight size={18} />
              </div>
            )}
          </button>
        </form>

        <div className="auth-links" style={{ marginTop: '24px' }}>
          <Link to="/login" style={{ textDecoration: 'none', color: '#2563eb', fontWeight: 600, fontSize: '14px' }}>
            Retour connexion
          </Link>
        </div>
      </div>
    </div>
  );
}
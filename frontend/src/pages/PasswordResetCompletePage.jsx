import { Eye, EyeOff, Lock, ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, getApiError } from "../api/api";
import AuthTriangles from "../components/AuthTriangles";

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
      <AuthTriangles />

      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Nouveau mot de passe</h1>
        <div className="rainbow-line" />

        <p className="subtitle" style={{ textAlign: 'center', marginBottom: '24px' }}>
          Choisissez un mot de passe fort et différent de l’ancien pour sécuriser votre accès.
        </p>

        {error && <div className="auth-error-banner">{error}</div>}
        {success && <div className="auth-error-banner" style={{ background: '#ecfdf5', borderColor: '#d1fae5', color: '#065f46' }}>{success}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Lock size={17} /></span>
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
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </div>

          <div className="input-group">
            <div className="input-icon-wrap">
              <span className="input-icon-left"><Lock size={17} /></span>
              <input
                className="input has-right-icon"
                type={showConfirmPassword ? "text" : "password"}
                value={form.confirmation_mot_de_passe}
                onChange={(event) =>
                  updateField("confirmation_mot_de_passe", event.target.value)
                }
                placeholder="Confirmer le mot de passe"
                required
              />
              <button
                type="button"
                className="input-icon-right"
                onClick={() => setShowConfirmPassword((v) => !v)}
                tabIndex={-1}
              >
                {showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </div>

          <button className="btn-primary" disabled={loading}>
            {loading ? "Enregistrement..." : "Changer le mot de passe"}
            {!loading && <ArrowRight size={18} />}
          </button>
        </form>

        <div className="auth-forgot" style={{ textAlign: 'center', marginTop: '24px' }}>
          <Link to="/login">Retour à la connexion</Link>
        </div>
      </div>
    </div>
  );
}
import { KeyRound } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, getApiError } from "../api/api";

export default function PasswordResetRecoveryTokenPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = useMemo(() => params.get("token") || "", [params]);
  const inputRef = useRef(null);

  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await api.post(
        "/auth/password-reset/recovery-token/verify",
        { token, code_secours: code },
        { skipAuthRedirect: true }
      );
      const data = response.data;

      if (!data.success) {
        setCode("");
        window.setTimeout(() => inputRef.current?.focus(), 0);
        setError(data.message || "Code de récupération invalide ou déjà utilisé.");
        return;
      }

      sessionStorage.setItem("reset_password_token", data.reset_password_token);
      navigate("/password-reset/complete");
    } catch (err) {
      setCode("");
      window.setTimeout(() => inputRef.current?.focus(), 0);
      setError(getApiError(err, "Vérification impossible."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>Utiliser un code de récupération</h1>
        <p>
          Saisissez l’un de vos codes de récupération pour continuer la
          réinitialisation de votre mot de passe.
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        <form className="form" onSubmit={handleSubmit}>
          <div className="input-group">
            <label>Code de récupération</label>
            <input
              ref={inputRef}
              className="input"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
              autoFocus
            />
          </div>

          <button className="btn btn-primary" disabled={loading || !token}>
            <KeyRound size={18} />
            {loading ? "Vérification..." : "Continuer"}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Retour connexion</Link>
        </div>
      </div>
    </div>
  );
}

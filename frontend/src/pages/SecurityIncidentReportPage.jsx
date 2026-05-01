import { AlertTriangle, CheckCircle2, Info, KeyRound } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

const contentByStatus = {
  success: {
    icon: CheckCircle2,
    boxClass: "success-security-box",
    title: "Signalement enregistré",
    subtitle: "Merci, votre signalement a été pris en compte.",
    message:
      "Par sécurité, toutes vos sessions actives ont été fermées. Votre compte reste temporairement protégé, et l’incident est enregistré dans le journal d’audit.",
  },
  already_reported: {
    icon: Info,
    boxClass: "success-security-box",
    title: "Signalement déjà pris en compte",
    subtitle: "Cette activité suspecte a déjà été signalée.",
    message:
      "Vos sessions actives ont déjà été fermées et l’incident est présent dans le journal d’audit.",
  },
  invalid: {
    icon: AlertTriangle,
    boxClass: "blocked-box",
    title: "Lien invalide ou expiré",
    subtitle: "Lien invalide ou expiré",
    message: "Ce lien de signalement n’est plus valide ou a expiré.",
  },
  error: {
    icon: AlertTriangle,
    boxClass: "blocked-box",
    title: "Signalement non confirmé",
    subtitle: "Erreur de sécurité",
    message:
      "Le signalement n’a pas pu être enregistré correctement. Veuillez changer votre mot de passe ou contacter l’administrateur.",
  },
};

export default function SecurityIncidentReportPage() {
  const [params] = useSearchParams();
  const status = params.get("status");
  const content = contentByStatus[status] || contentByStatus.invalid;
  const Icon = content.icon;

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />

        <h1>{content.title}</h1>

        <div className={content.boxClass}>
          {content.boxClass === "blocked-box" ? (
            <div className="blocked-icon">
              <Icon size={34} />
            </div>
          ) : (
            <Icon size={42} />
          )}

          <h2>{content.subtitle}</h2>
          <p>{content.message}</p>
        </div>

        <div className="form" style={{ marginTop: 28 }}>
          <Link to="/forgot-password" className="btn btn-danger">
            <KeyRound size={18} />
            Changer mon mot de passe
          </Link>

          <Link to="/login" className="btn btn-secondary">
            Retour à la connexion
          </Link>
        </div>
      </div>
    </div>
  );
}

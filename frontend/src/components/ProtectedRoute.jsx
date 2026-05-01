import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, adminOnly = false, superAdminOnly = false }) {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
          <div className="alert alert-info">Chargement de votre session...</div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!user) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <img src="/tt-logo.png" alt="Tunisie Telecom" className="auth-logo" />
          <div className="alert alert-info">Vérification de votre session...</div>
        </div>
      </div>
    );
  }

  if (superAdminOnly && user.role !== "SUPER_ADMIN") {
    return <Navigate to="/access-denied" replace />;
  }

  if (adminOnly && !["ADMIN", "SUPER_ADMIN"].includes(user.role)) {
    return <Navigate to="/access-denied" replace />;
  }

  return children;
}

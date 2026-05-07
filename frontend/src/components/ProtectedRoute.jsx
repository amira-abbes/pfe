import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function hasAnyRequiredRight(hasRight, requiredRight, requiredAnyRight = []) {
  const requiredRights = [
    ...(requiredRight ? [requiredRight] : []),
    ...requiredAnyRight,
  ];

  if (requiredRights.length === 0) return true;
  return requiredRights.some((right) => hasRight(right));
}

export default function ProtectedRoute({
  children,
  adminOnly = false,
  superAdminOnly = false,
  requiredRight,
  requiredAnyRight = [],
}) {
  const { hasRight, isAuthenticated, loading, user } = useAuth();

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

  if (!hasAnyRequiredRight(hasRight, requiredRight, requiredAnyRight)) {
    return <Navigate to="/access-denied" replace />;
  }

  return children;
}

import { Navigate } from "react-router-dom";
import { firstAuthorizedPath } from "../accessControl";
import { useAuth } from "../context/AuthContext";

const DEPARTMENT_ADMIN_ROLES = ["ADMIN", "ADMIN_DEPARTEMENTAL"];

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
  departmentAdminOnly = false,
  superAdminOnly = false,
  requiredRight,
  requiredAnyRight = [],
}) {
  const { hasRight, isAuthenticated, loading, user } = useAuth();
  const authorizedFallback = firstAuthorizedPath(user);

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
    return <Navigate to={authorizedFallback} replace />;
  }

  if (departmentAdminOnly && !DEPARTMENT_ADMIN_ROLES.includes(user.role)) {
    return <Navigate to={authorizedFallback} replace />;
  }

  if (adminOnly && ![...DEPARTMENT_ADMIN_ROLES, "SUPER_ADMIN"].includes(user.role)) {
    return <Navigate to={authorizedFallback} replace />;
  }

  if (!hasAnyRequiredRight(hasRight, requiredRight, requiredAnyRight)) {
    return <Navigate to={authorizedFallback} replace />;
  }

  return children;
}

import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";

import LoginPage from "./pages/LoginPage";
import TotpPage from "./pages/TotpPage";
import RecoveryCodePage from "./pages/RecoveryCodePage";
import MfaRecoveryCodeLinkPage from "./pages/MfaRecoveryCodeLinkPage";
import MfaResetPage from "./pages/MfaResetPage";
import MfaSetupPage from "./pages/MfaSetupPage";
import MfaBlockedPage from "./pages/MfaBlockedPage";
import SessionExpiredPage from "./pages/SessionExpiredPage";
import PasswordErrorPage from "./pages/PasswordErrorPage";
import MailVerificationRequiredPage from "./pages/MailVerificationRequiredPage";
import AccessDeniedPage from "./pages/AccessDeniedPage";
import AccountDisabledPage from "./pages/AccountDisabledPage";

import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import PasswordResetVerifyPage from "./pages/PasswordResetVerifyPage";
import PasswordResetMfaPage from "./pages/PasswordResetMfaPage";
import PasswordResetCompletePage from "./pages/PasswordResetCompletePage";
import PasswordResetRecoveryTokenPage from "./pages/PasswordResetRecoveryTokenPage";

import ActivationPage from "./pages/ActivationPage";
import ActivationTotpPage from "./pages/ActivationTotpPage";

import UserDashboard from "./pages/UserDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminDepartmentsPage from "./pages/AdminDepartmentsPage";
import AdminEltPage from "./pages/AdminEltPage";
import DashboardServiceSosPage from "./pages/DashboardServiceSosPage";
import DashboardParcServiceSosPage from "./pages/DashboardParcServiceSosPage";
import DashboardBadDebtsPage from "./pages/DashboardBadDebtsPage";

import AccountSecurityPage from "./pages/AccountSecurityPage";
import SecurityIncidentReportPage from "./pages/SecurityIncidentReportPage";
import SecurityReportPage from "./pages/SecurityReportPage";
import SecureRecoveryPage from "./pages/SecureRecoveryPage";
import RecoveryCodesRegenerateLinkPage from "./pages/RecoveryCodesRegenerateLinkPage";
import RecoverySupervisorActionPage from "./pages/RecoverySupervisorActionPage";
import ReactivationActionPage from "./pages/ReactivationActionPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />

      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/totp" element={<TotpPage />} />
      <Route path="/mfa/verify" element={<TotpPage />} />
      <Route path="/auth/recovery-code" element={<RecoveryCodePage />} />
      <Route path="/mfa/recovery-code" element={<MfaRecoveryCodeLinkPage />} />
      <Route path="/mfa/reset" element={<MfaResetPage />} />
      <Route path="/mfa/setup" element={<MfaSetupPage />} />
      <Route path="/mfa-blocked" element={<MfaBlockedPage />} />

      <Route path="/session-expired" element={<SessionExpiredPage />} />
      <Route path="/password-error" element={<PasswordErrorPage />} />
      <Route path="/password-lockout" element={<PasswordErrorPage />} />
      <Route path="/mail-verification-required" element={<MailVerificationRequiredPage />} />
      <Route path="/access-denied" element={<AccessDeniedPage />} />
      <Route path="/account-disabled" element={<AccountDisabledPage />} />

      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/password-reset" element={<PasswordResetVerifyPage />} />
      <Route
        path="/password-reset/from-lockout"
        element={<PasswordResetVerifyPage />}
      />
      <Route path="/password-reset/mfa" element={<PasswordResetMfaPage />} />
      <Route
        path="/password-reset/complete"
        element={<PasswordResetCompletePage />}
      />
      <Route
        path="/recovery-code/verify"
        element={<PasswordResetRecoveryTokenPage />}
      />

      <Route path="/activation" element={<ActivationPage />} />
      <Route path="/activation/totp" element={<ActivationTotpPage />} />

      <Route
        path="/security/incident-report"
        element={<SecurityIncidentReportPage />}
      />
      <Route path="/security/report" element={<SecurityReportPage />} />
      <Route path="/secure-recovery" element={<SecureRecoveryPage />} />
      <Route
        path="/recovery-codes/regenerate"
        element={<RecoveryCodesRegenerateLinkPage />}
      />
      <Route
        path="/security/recovery-action"
        element={<RecoverySupervisorActionPage />}
      />
      <Route
        path="/security/reactivation-action"
        element={<ReactivationActionPage />}
      />

      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <UserDashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/user/dashboard"
        element={
          <ProtectedRoute>
            <UserDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/security"
        element={
          <ProtectedRoute>
            <AccountSecurityPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/super-admin/dashboard"
        element={
          <ProtectedRoute superAdminOnly>
            <AdminDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/dashboard"
        element={
          <ProtectedRoute adminOnly>
            <AdminDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/users"
        element={
          <ProtectedRoute adminOnly requiredRight="gerer_utilisateurs">
            <AdminUsersPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/departements"
        element={
          <ProtectedRoute adminOnly requiredAnyRight={["gerer_departements", "gerer_roles"]}>
            <AdminDepartmentsPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/elt"
        element={
          <ProtectedRoute requiredRight="lancer_elt">
            <AdminEltPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/dashboard/service-sos"
        element={
          <ProtectedRoute requiredRight="dashboard_service_sos">
            <DashboardServiceSosPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/dashboard/parc-service-sos"
        element={
          <ProtectedRoute requiredRight="dashboard_parc_service_sos">
            <DashboardParcServiceSosPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/dashboard/bad-debts"
        element={
          <ProtectedRoute requiredRight="dashboard_bad_debts">
            <DashboardBadDebtsPage />
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

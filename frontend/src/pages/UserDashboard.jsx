import {
  Building2,
  Edit2,
  KeyRound,
  Mail,
  Shield,
  User,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/api";
import Layout from "../components/Layout";
import PageHeader from "../components/PageHeader";
import { useAuth } from "../context/AuthContext";

export default function UserDashboard() {
  const { user } = useAuth();
  const [securityStatus, setSecurityStatus] = useState(null);
  const [securityUnavailable, setSecurityUnavailable] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const response = await api.get("/auth/security/recovery-codes/status", { skipAuthRedirect: true });
        setSecurityStatus(response.data);
      } catch (err) {
        console.error("Error loading dashboard data:", err);
        setSecurityUnavailable(true);
      }
    }

    loadData();
  }, []);

  return (
    <Layout>
      <PageHeader eyebrow="Compte" title="Mon compte" subtitle="Consultez vos informations personnelles et votre statut d’accès." />

      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'stretch', 
        gap: '24px', 
        maxWidth: '1000px', 
        margin: '0 auto', 
        padding: '0 24px',
        flexWrap: 'wrap'
      }}>
        {/* Left Card: Profile */}
        <div className="au-table-card au-card-with-header" style={{ flex: 1, minWidth: '320px', maxWidth: '480px', margin: 0 }}>
          <div className="au-card-header-bg purple">
            <div className="au-dot-pattern" />
          </div>
          
          <div className="au-card-content-relative" style={{ padding: "0 24px 24px" }}>
            <div className="au-avatar-circle-bordered">
              <User size={40} />
            </div>
            
            <h2 className="au-profile-name-lg" style={{ textTransform: 'capitalize' }}>
              {user?.nom_complet?.toLowerCase()}
            </h2>
            
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '24px' }}>
              <span className="au-badge au-badge-blue" style={{ padding: '4px 16px', borderRadius: '50px' }}>
                UTILISATEUR
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', color: '#475569', fontSize: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Mail size={18} style={{ color: '#94a3b8' }} />
                <span>{user?.email}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Building2 size={18} style={{ color: '#94a3b8' }} />
                <span>{user?.departement_nom || "Commercial"}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Shield size={18} style={{ color: '#94a3b8' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>Statut :</span>
                  <span className="au-badge au-badge-green">ACTIVE</span>
                </div>
              </div>
            </div>

            <button className="au-btn-outline-blue">
              <Edit2 size={16} />
              Modifier mes informations
            </button>
          </div>
        </div>

        {/* Right Card: Security */}
        <div className="au-table-card au-card-with-header" style={{ flex: 1, minWidth: '320px', maxWidth: '480px', margin: 0 }}>
          <div className="au-card-header-bg green">
            <div className="au-dot-pattern" />
          </div>

          <div className="au-card-content-relative" style={{ padding: "0 24px 24px", textAlign: 'center' }}>
            <div className="au-shield-circle">
              <Shield size={40} />
            </div>

            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#1e293b', margin: '16px 0 4px' }}>
              Sécurité du compte
            </h3>
            <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
              Authentification forte active
            </p>

            <div style={{ padding: '32px 0' }}>
              <div style={{ fontSize: '48px', fontWeight: 800, color: '#2563eb', lineHeight: 1 }}>
                {securityStatus ? securityStatus.codes_restants : "--"}
              </div>
              <div style={{ fontSize: '14px', color: '#64748b', fontWeight: 600, marginTop: '8px' }}>
                Codes de secours restants
              </div>
            </div>

            <Link
              to="/security"
              className="au-btn-create"
              style={{ width: "100%", justifyContent: "center", padding: "14px", borderRadius: '50px' }}
            >
              <KeyRound size={18} />
              Gérer mes codes de secours
            </Link>

            <Link to="/security" style={{ display: 'block', marginTop: '16px', fontSize: '13px', color: '#2563eb', textDecoration: 'none', fontWeight: 600 }}>
              En savoir plus sur la sécurité →
            </Link>
          </div>
        </div>
      </div>
    </Layout>
  );
}

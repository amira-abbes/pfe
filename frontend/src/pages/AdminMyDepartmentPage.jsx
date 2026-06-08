import {
  CheckCircle2,
  EllipsisVertical,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserCheck,
  Users,
  UserX,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import PageHeader from "../components/PageHeader";
import { useAuth } from "../context/AuthContext";

const STATUS_LABELS = {
  ACTIF: "Actif",
  EN_ATTENTE_PREMIERE_CONNEXION: "En attente de première connexion",
  DESACTIVE_ADMIN: "Désactivé",
  BLOQUE_TENTATIVES: "Bloqué",
  SUPPRIME: "Supprimé",
};

const STATUS_CLASSES = {
  ACTIF: "is-active",
  EN_ATTENTE_PREMIERE_CONNEXION: "is-pending",
  DESACTIVE_ADMIN: "is-inactive",
  BLOQUE_TENTATIVES: "is-blocked",
  SUPPRIME: "is-deleted",
};

function normalizeStatus(item) {
  if (item.date_suppression) return "SUPPRIME";
  const raw = String(item.statut_compte || "").toUpperCase();
  if (raw === "ACTIVE") return "ACTIF";
  if (raw === "PENDING_ACTIVATION" || raw === "MFA_SETUP_REQUIRED") {
    return "EN_ATTENTE_PREMIERE_CONNEXION";
  }
  if (raw === "DISABLED") return "DESACTIVE_ADMIN";
  return raw;
}

function splitFullName(fullName = "") {
  const parts = String(fullName).trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) {
    return { prenom: parts[0] || "-", nom: "-" };
  }
  return { prenom: parts[0], nom: parts.slice(1).join(" ") };
}

function roleClass(role) {
  return String(role || "USER").toLowerCase().replaceAll("_", "");
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

export default function AdminMyDepartmentPage() {
  const { user: currentUser } = useAuth();
  const departmentName = currentUser?.departement_nom || "";

  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ email: "", nom_complet: "" });
  const [search, setSearch] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [debugLink, setDebugLink] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadUsers() {
    setError("");
    try {
      const response = await api.get("/admin/users");
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch (err) {
      setError(getApiError(err, "Erreur chargement utilisateurs du département."));
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function createUser(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setDebugLink("");
    setLoading(true);

    try {
      const response = await api.post("/admin/users", {
        email: form.email,
        nom_complet: form.nom_complet,
      });
      setMessage(response.data.message || "Utilisateur créé. Un email d'activation a été envoyé.");
      setDebugLink(response.data.activation_link_debug || "");
      setForm({ email: "", nom_complet: "" });
      setDrawerOpen(false);
      await loadUsers();
    } catch (err) {
      setError(getApiError(err, "Erreur création utilisateur."));
    } finally {
      setLoading(false);
    }
  }

  async function toggleStatus(item) {
    const action = item.est_actif ? "désactiver" : "réactiver";
    if (!confirm(`Voulez-vous ${action} le compte ${item.email} ?`)) return;

    setError("");
    setMessage("");
    try {
      const response = await api.patch(
        `/admin/users/by-email/${encodeURIComponent(item.email)}/status`,
        { est_actif: !item.est_actif }
      );
      setMessage(response.data.message || "Statut utilisateur mis à jour.");
      await loadUsers();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour statut."));
    }
  }

  async function deleteUser(item) {
    if (!confirm(`Supprimer l'utilisateur ${item.email} ?`)) return;

    setError("");
    setMessage("");
    try {
      await api.delete(`/admin/users/by-email/${encodeURIComponent(item.email)}`);
      setMessage("Utilisateur supprimé.");
      await loadUsers();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression utilisateur."));
    }
  }

  async function regenerateRecoveryCodes(item) {
    if (!confirm(`Régénérer les codes de secours de ${item.email} et les envoyer par email ?`)) return;

    setError("");
    setMessage("");
    try {
      const response = await api.post(
        `/admin/users/by-email/${encodeURIComponent(item.email)}/recovery-codes/regenerate`
      );
      setMessage(response.data.message || "Codes de secours régénérés.");
    } catch (err) {
      setError(getApiError(err, "Erreur régénération codes de secours."));
    }
  }

  function canDeactivate(item) {
    return item.est_actif && normalizeStatus(item) === "ACTIF";
  }

  function canReactivate(item) {
    return !item.est_actif && ["DESACTIVE_ADMIN", "BLOQUE_TENTATIVES"].includes(normalizeStatus(item));
  }

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return users;
    return users.filter((item) =>
      [item.nom_complet, item.email, item.role, item.statut_compte]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [users, search]);

  const totalUsers = users.length;
  const activeUsers = users.filter((item) => item.est_actif).length;
  const inactiveUsers = totalUsers - activeUsers;

  return (
    <Layout>
      <main className="users-admin-page my-department-page">
        <PageHeader
          eyebrow="Administration"
          title="Mon département"
          subtitle={`Gérez les utilisateurs rattachés à ${departmentName || "votre département"}.`}
          action={<button className="users-create-button" onClick={() => { setDrawerOpen(true); setMessage(""); setError(""); }}><Plus size={18} />Ajouter un utilisateur</button>}
        />

      {error && <div className="au-alert au-alert-error">{error}</div>}
      {message && <div className="au-alert au-alert-success">{message}</div>}
      {debugLink && <div className="au-alert au-alert-debug">Lien activation debug : <a href={debugLink}>{debugLink}</a></div>}

      <div className="users-kpi-grid my-department-kpis">
        <div className="users-kpi-card users-kpi-total">
          <div className="users-kpi-icon">
            <Users size={24} />
          </div>
          <div>
            <strong>{totalUsers}</strong>
            <span>Total utilisateurs</span>
          </div>
        </div>
        <div className="users-kpi-card users-kpi-active">
          <div className="users-kpi-icon">
            <UserCheck size={24} />
          </div>
          <div>
            <strong>{activeUsers}</strong>
            <span>Comptes actifs</span>
          </div>
        </div>
        <div className="users-kpi-card users-kpi-inactive">
          <div className="users-kpi-icon">
            <UserX size={24} />
          </div>
          <div>
            <strong>{inactiveUsers}</strong>
            <span>Comptes inactifs</span>
          </div>
        </div>
      </div>

      <div className="users-control-panel my-department-controls">
        <div className="users-search-field">
          <Search size={18} />
          <input
            placeholder="Rechercher par nom, email, rôle ou statut…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="users-filter-group">
          <button className="users-refresh-button" onClick={loadUsers} title="Actualiser">
            <RefreshCw size={17} />
          </button>
        </div>
        <div className="users-results-meta">
          <strong>{filteredUsers.length}</strong> utilisateur{filteredUsers.length > 1 ? "s" : ""} trouvé{filteredUsers.length > 1 ? "s" : ""}
        </div>
      </div>

      <div className="users-table-shell">
        <div className="users-table-scroll">
          <table className="users-premium-table my-department-table">
            <thead>
              <tr>
                <th>Prénom</th>
                <th>Nom</th>
                <th>Email</th>
                <th>Rôle</th>
                <th>Statut</th>
                <th>Date création</th>
                <th className="users-actions-heading">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((item) => {
                const status = normalizeStatus(item);
                const { prenom, nom } = splitFullName(item.nom_complet);
                return (
                  <tr key={item.id}>
                    <td className="au-td-name">{prenom}</td>
                    <td className="au-td-name">{nom}</td>
                    <td className="au-td-email">{item.email}</td>
                    <td><span className={`users-role-badge role-${roleClass(item.role)}`}>{item.role}</span></td>
                    <td>
                      <span className={`users-status-badge ${STATUS_CLASSES[status] || "is-pending"}`}>
                        <i />{STATUS_LABELS[status] || status}
                      </span>
                    </td>
                    <td><span className="users-last-login">{formatDate(item.date_creation)}</span></td>
                    <td className="users-actions-cell">
                      <details className="users-action-dropdown">
                        <summary aria-label={`Actions pour ${item.email}`}><EllipsisVertical size={19} /></summary>
                        <div className="users-action-menu">
                          <button onClick={() => regenerateRecoveryCodes(item)}><KeyRound size={15} /> Codes de secours</button>
                          {canDeactivate(item) && (
                            <button onClick={() => toggleStatus(item)}><UserX size={15} /> Désactiver</button>
                          )}
                          {canReactivate(item) && (
                            <button onClick={() => toggleStatus(item)}><CheckCircle2 size={15} /> {status === "BLOQUE_TENTATIVES" ? "Débloquer" : "Réactiver"}</button>
                          )}
                          <button className="is-danger" onClick={() => deleteUser(item)}><Trash2 size={15} /> Supprimer</button>
                        </div>
                      </details>
                    </td>
                  </tr>
                );
              })}

              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan="7" className="users-table-state my-department-empty">
                    <Users size={25} />
                    <strong>Aucun utilisateur trouvé</strong>
                    <span>{search ? "Modifiez votre recherche pour afficher d'autres résultats." : "Les utilisateurs ajoutés au département apparaîtront ici."}</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      </main>

      {drawerOpen && <div className="au-overlay" onClick={() => setDrawerOpen(false)} />}

      <div className={`au-drawer ${drawerOpen ? "au-drawer-open" : ""}`}>
        <div className="au-drawer-header">
          <div>
            <h2 className="au-drawer-title">Ajouter un utilisateur</h2>
            <p className="au-drawer-hint">
              Le nouvel utilisateur sera automatiquement rattaché à votre département.
            </p>
          </div>
          <button className="au-drawer-close" onClick={() => setDrawerOpen(false)}>
            <X size={20} />
          </button>
        </div>

        <div className="alert alert-info" style={{ margin: "0 0 16px", fontSize: 13 }}>
          Département : <strong>{departmentName || "Non défini"}</strong>
        </div>

        <form className="au-drawer-form" onSubmit={createUser}>
          <div className="au-field">
            <label className="au-label">Email</label>
            <input
              className="au-input"
              type="email"
              value={form.email}
              onChange={(event) => updateField("email", event.target.value)}
              placeholder="utilisateur@tunisietelecom.tn"
              required
            />
          </div>

          <div className="au-field">
            <label className="au-label">Nom complet</label>
            <input
              className="au-input"
              value={form.nom_complet}
              onChange={(event) => updateField("nom_complet", event.target.value)}
              placeholder="Prénom Nom"
              required
            />
          </div>

          <div className="au-field">
            <label className="au-label">Rôle</label>
            <div className="au-input au-input-readonly">USER</div>
          </div>

          <button className="au-btn-submit" type="submit" disabled={loading || !departmentName}>
            <Plus size={18} />
            {loading ? "Création en cours..." : "Créer l'utilisateur"}
          </button>
        </form>
      </div>
    </Layout>
  );
}

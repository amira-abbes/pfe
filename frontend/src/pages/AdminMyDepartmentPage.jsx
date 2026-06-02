import { Plus, RefreshCw, Search, UserCheck, Users, UserX, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

const STATUS_LABELS = {
  ACTIF: "Actif",
  EN_ATTENTE_PREMIERE_CONNEXION: "En attente de première connexion",
  DESACTIVE_ADMIN: "Désactivé",
  BLOQUE_TENTATIVES: "Bloqué",
  SUPPRIME: "Supprimé",
};

const STATUS_CLASSES = {
  ACTIF: "au-badge au-badge-green",
  EN_ATTENTE_PREMIERE_CONNEXION: "au-badge au-badge-orange",
  DESACTIVE_ADMIN: "au-badge au-badge-orange",
  BLOQUE_TENTATIVES: "au-badge au-badge-red",
  SUPPRIME: "au-badge au-badge-gray",
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
      <div className="au-page-header">
        <div>
          <h1 className="au-page-title">Mon département</h1>
          <p className="au-page-sub">
            Gestion des utilisateurs rattachés à {departmentName || "votre département"}.
          </p>
        </div>
        <button
          className="au-btn-create"
          onClick={() => { setDrawerOpen(true); setMessage(""); setError(""); }}
        >
          <Plus size={18} />
          Ajouter un utilisateur
        </button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
      {message && <div className="alert alert-success" style={{ marginBottom: 16 }}>{message}</div>}
      {debugLink && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          Lien activation debug : <a href={debugLink}>{debugLink}</a>
        </div>
      )}

      <div className="au-stats-row">
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#e0e7ff", color: "#4f46e5" }}>
            <Users size={24} />
          </div>
          <div>
            <div className="au-stat-value">{totalUsers}</div>
            <div className="au-stat-label">Total utilisateurs</div>
          </div>
        </div>
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#dcfce7", color: "#16a34a" }}>
            <UserCheck size={24} />
          </div>
          <div>
            <div className="au-stat-value" style={{ color: "#16a34a" }}>{activeUsers}</div>
            <div className="au-stat-label">Utilisateurs actifs</div>
          </div>
        </div>
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#fee2e2", color: "#dc2626" }}>
            <UserX size={24} />
          </div>
          <div>
            <div className="au-stat-value" style={{ color: "#dc2626" }}>{inactiveUsers}</div>
            <div className="au-stat-label">Utilisateurs désactivés</div>
          </div>
        </div>
      </div>

      <div className="au-filter-bar">
        <div className="au-search-wrap">
          <Search size={16} className="au-search-icon" />
          <input
            className="au-search-input"
            placeholder="Rechercher par nom, prénom ou email..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <button className="au-refresh-btn" onClick={loadUsers} title="Actualiser">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="au-table-card">
        <div className="au-table-wrap">
          <table className="au-table">
            <thead>
              <tr>
                <th>Prénom</th>
                <th>Nom</th>
                <th>Email</th>
                <th>Rôle</th>
                <th>Statut</th>
                <th>Date création</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((item) => {
                const status = normalizeStatus(item);
                const { prenom, nom } = splitFullName(item.nom_complet);
                return (
                  <tr key={item.id} className="au-table-row">
                    <td className="au-td-name">{prenom}</td>
                    <td className="au-td-name">{nom}</td>
                    <td className="au-td-email">{item.email}</td>
                    <td><span className="au-role-badge">{item.role}</span></td>
                    <td>
                      <span className={STATUS_CLASSES[status] || "au-badge au-badge-orange"}>
                        {STATUS_LABELS[status] || status}
                      </span>
                    </td>
                    <td className="au-td-text">{formatDate(item.date_creation)}</td>
                    <td>
                      <div className="au-actions">
                        {canDeactivate(item) && (
                          <button className="au-btn-toggle" onClick={() => toggleStatus(item)}>
                            Désactiver
                          </button>
                        )}
                        {canReactivate(item) && (
                          <button className="au-btn-toggle" onClick={() => toggleStatus(item)}>
                            {status === "BLOQUE_TENTATIVES" ? "Débloquer" : "Réactiver"}
                          </button>
                        )}
                        <button className="au-btn-toggle" onClick={() => regenerateRecoveryCodes(item)}>
                          Codes secours
                        </button>
                        <button className="au-btn-delete" onClick={() => deleteUser(item)}>
                          <UserX size={14} />
                          Supprimer
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan="7" className="au-empty-row">
                    Aucun utilisateur dans ce département.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

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

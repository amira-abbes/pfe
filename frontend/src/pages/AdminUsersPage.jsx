import { Plus, RefreshCw, Search, UserX, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

const ITEMS_PER_PAGE = 10;

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();

  const isSuperAdmin = currentUser?.role === "SUPER_ADMIN";
  const isAdmin = currentUser?.role === "ADMIN";

  // ── Core state (unchanged logic) ──────────────────────────────────────────
  const [users, setUsers] = useState([]);
  const [departements, setDepartements] = useState([]);
  const [form, setForm] = useState({
    email: "",
    nom_complet: "",
    departement_nom: "",
    role: "USER",
  });
  const [message, setMessage] = useState("");
  const [debugLink, setDebugLink] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // ── UI state ───────────────────────────────────────────────────────────────
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [page, setPage] = useState(1);

  // ── Data loading (unchanged logic) ────────────────────────────────────────
  async function loadData() {
    setError("");
    try {
      if (isSuperAdmin) {
        const [usersResponse, depsResponse] = await Promise.all([
          api.get("/admin/users"),
          api.get("/admin/departements"),
        ]);
        const deps = Array.isArray(depsResponse.data) ? depsResponse.data : [];
        setUsers(usersResponse.data);
        setDepartements(deps);
        setForm((c) => ({
          ...c,
          departement_nom:
            c.departement_nom && deps.some((d) => d.nom_departement === c.departement_nom)
              ? c.departement_nom
              : deps[0]?.nom_departement || "",
        }));
      } else {
        const usersResponse = await api.get("/admin/users");
        setUsers(usersResponse.data);
        setDepartements([]);
        setForm((c) => ({ ...c, departement_nom: currentUser?.departement_nom || "", role: "USER" }));
      }
    } catch (err) {
      setError(getApiError(err, "Erreur chargement utilisateurs."));
    }
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperAdmin, currentUser?.departement_nom]);

  function updateField(field, value) {
    setForm((c) => ({ ...c, [field]: value }));
  }

  // ── Create user (unchanged logic) ─────────────────────────────────────────
  async function createUser(event) {
    event.preventDefault();
    setError(""); setMessage(""); setDebugLink(""); setLoading(true);
    try {
      const payload = {
        email: form.email,
        nom_complet: form.nom_complet,
        role: isSuperAdmin ? form.role : "USER",
        departement_nom: isSuperAdmin
          ? form.departement_nom
          : currentUser?.departement_nom || form.departement_nom || "",
      };
      const response = await api.post("/admin/users", payload);
      setMessage(response.data.message || "Utilisateur créé.");
      setDebugLink(response.data.activation_link_debug || "");
      setForm((c) => ({ ...c, email: "", nom_complet: "", role: "USER" }));
      await loadData();
      setDrawerOpen(false);
    } catch (err) {
      setError(getApiError(err, "Erreur création utilisateur."));
    } finally {
      setLoading(false);
    }
  }

  // ── Toggle status (unchanged logic) ───────────────────────────────────────
  async function toggleStatus(user) {
    const action = user.est_actif ? "désactiver" : "réactiver";
    if (!confirm(`Voulez-vous ${action} le compte ${user.email} ?`)) return;
    setError(""); setMessage("");
    try {
      const response = await api.patch(
        `/admin/users/by-email/${encodeURIComponent(user.email)}/status`,
        { est_actif: !user.est_actif }
      );
      setMessage(response.data.message || "Statut utilisateur mis à jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour statut."));
    }
  }

  // ── Update profile (unchanged logic) ──────────────────────────────────────
  async function updateUserProfile(user, changes) {
    if (!isSuperAdmin) return;
    setError(""); setMessage("");
    try {
      await api.patch(`/admin/users/by-email/${encodeURIComponent(user.email)}/profile`, {
        role: changes.role || user.role,
        departement_nom: changes.departement_nom || user.departement_nom || departements[0]?.nom_departement || "",
      });
      setMessage("Profil utilisateur mis à jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour profil utilisateur."));
    }
  }

  // ── Delete user (unchanged logic) ─────────────────────────────────────────
  async function deleteUser(user) {
    if (!confirm(`Supprimer l'utilisateur ${user.email} ?`)) return;
    setError(""); setMessage("");
    try {
      await api.delete(`/admin/users/by-email/${encodeURIComponent(user.email)}`);
      setMessage("Utilisateur supprimé.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression utilisateur."));
    }
  }

  // ── Derived / filtered data ────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return users.filter((u) => {
      const matchSearch = !q || u.email?.toLowerCase().includes(q) || u.nom_complet?.toLowerCase().includes(q);
      const matchDept = !filterDept || u.departement_nom === filterDept;
      const matchRole = !filterRole || u.role === filterRole;
      const matchStatus = !filterStatus || (filterStatus === "actif" ? u.est_actif : !u.est_actif);
      return matchSearch && matchDept && matchRole && matchStatus;
    });
  }, [users, search, filterDept, filterRole, filterStatus]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const paginated = filtered.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const totalUsers = users.length;
  const activeUsers = users.filter((u) => u.est_actif).length;
  const inactiveUsers = totalUsers - activeUsers;
  const uniqueDepts = [...new Set(users.map((u) => u.departement_nom).filter(Boolean))];

  return (
    <Layout>
      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div className="au-page-header">
        <div>
          <h1 className="au-page-title">Gestion Utilisateurs</h1>
          <p className="au-page-sub">Gérez les comptes, rôles et accès de votre équipe.</p>
        </div>
        <button
          className="au-btn-create"
          onClick={() => { setDrawerOpen(true); setMessage(""); setError(""); }}
        >
          <Plus size={18} />
          Créer un utilisateur
        </button>
      </div>

      {/* ── Global alerts ───────────────────────────────────────────────────── */}
      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
      {message && <div className="alert alert-success" style={{ marginBottom: 16 }}>{message}</div>}
      {debugLink && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          Lien activation debug : <a href={debugLink}>{debugLink}</a>
        </div>
      )}

      {/* ── Stats cards ─────────────────────────────────────────────────────── */}
      <div className="au-stats-row">
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#eff6ff", color: "#2563eb" }}>👥</div>
          <div>
            <div className="au-stat-value">{totalUsers}</div>
            <div className="au-stat-label">Total Utilisateurs</div>
          </div>
        </div>
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#f0fdf4", color: "#10b981" }}>✅</div>
          <div>
            <div className="au-stat-value" style={{ color: "#10b981" }}>{activeUsers}</div>
            <div className="au-stat-label">Comptes Actifs</div>
          </div>
        </div>
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#fef2f2", color: "#ef4444" }}>🚫</div>
          <div>
            <div className="au-stat-value" style={{ color: "#ef4444" }}>{inactiveUsers}</div>
            <div className="au-stat-label">Comptes Inactifs</div>
          </div>
        </div>
      </div>

      {/* ── Search & filters ────────────────────────────────────────────────── */}
      <div className="au-filter-bar">
        <div className="au-search-wrap">
          <Search size={16} className="au-search-icon" />
          <input
            className="au-search-input"
            placeholder="Rechercher par nom, email..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>

        {isSuperAdmin && (
          <select
            className="au-filter-select"
            value={filterDept}
            onChange={(e) => { setFilterDept(e.target.value); setPage(1); }}
          >
            <option value="">Tous les départements</option>
            {uniqueDepts.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        )}

        <select
          className="au-filter-select"
          value={filterRole}
          onChange={(e) => { setFilterRole(e.target.value); setPage(1); }}
        >
          <option value="">Tous les rôles</option>
          <option value="USER">USER</option>
          <option value="ADMIN">ADMIN</option>
          <option value="SUPER_ADMIN">SUPER_ADMIN</option>
        </select>

        <select
          className="au-filter-select"
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
        >
          <option value="">Tous les statuts</option>
          <option value="actif">Actif</option>
          <option value="inactif">Inactif</option>
        </select>

        <button className="au-refresh-btn" onClick={loadData} title="Actualiser">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* ── Users table ─────────────────────────────────────────────────────── */}
      <div className="au-table-card">
        <div className="au-table-wrap">
          <table className="au-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Nom</th>
                <th>Département</th>
                <th>Rôle</th>
                <th>Statut</th>
                <th>Actif</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((item) => (
                <tr key={item.id} className="au-table-row">
                  <td className="au-td-email">{item.email}</td>
                  <td className="au-td-name">{item.nom_complet}</td>

                  <td>
                    {isSuperAdmin ? (
                      <select
                        className="au-inline-select"
                        value={item.departement_nom || ""}
                        onChange={(e) => updateUserProfile(item, { departement_nom: e.target.value })}
                      >
                        <option value="">Aucun</option>
                        {departements.map((dep) => (
                          <option key={dep.id} value={dep.nom_departement}>{dep.nom_departement}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="au-td-text">{item.departement_nom || "—"}</span>
                    )}
                  </td>

                  <td>
                    {isSuperAdmin ? (
                      <select
                        className="au-inline-select"
                        value={item.role}
                        onChange={(e) => updateUserProfile(item, { role: e.target.value })}
                      >
                        <option value="USER">USER</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    ) : (
                      <span className="au-role-badge">{item.role}</span>
                    )}
                  </td>

                  <td>
                    <span className={item.est_actif && item.statut_compte === "ACTIVE" ? "au-badge au-badge-green" : "au-badge au-badge-red"}>
                      {item.est_actif ? item.statut_compte : "Désactivé"}
                    </span>
                  </td>

                  <td>
                    <span className={item.est_actif ? "au-badge au-badge-green" : "au-badge au-badge-red"}>
                      {item.est_actif ? "Oui" : "Non"}
                    </span>
                  </td>

                  <td>
                    <div className="au-actions">
                      <button className="au-btn-toggle" onClick={() => toggleStatus(item)}>
                        {item.est_actif ? "Désactiver" : "Réactiver"}
                      </button>
                      <button className="au-btn-delete" onClick={() => deleteUser(item)}>
                        <UserX size={14} />
                        Supprimer
                      </button>
                    </div>
                  </td>
                </tr>
              ))}

              {paginated.length === 0 && (
                <tr>
                  <td colSpan="7" className="au-empty-row">
                    {search ? "Aucun résultat pour cette recherche." : "Aucun utilisateur."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="au-pagination">
            <button className="au-page-btn" disabled={page === 1} onClick={() => setPage(page - 1)}>‹</button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                className={`au-page-btn ${p === page ? "au-page-btn-active" : ""}`}
                onClick={() => setPage(p)}
              >
                {p}
              </button>
            ))}
            <button className="au-page-btn" disabled={page === totalPages} onClick={() => setPage(page + 1)}>›</button>
          </div>
        )}
      </div>

      {/* ── Drawer overlay ──────────────────────────────────────────────────── */}
      {drawerOpen && <div className="au-overlay" onClick={() => setDrawerOpen(false)} />}

      {/* ── Drawer panel ────────────────────────────────────────────────────── */}
      <div className={`au-drawer ${drawerOpen ? "au-drawer-open" : ""}`}>
        <div className="au-drawer-header">
          <div>
            <h2 className="au-drawer-title">Créer un utilisateur</h2>
            <p className="au-drawer-hint">
              Après création, l'utilisateur reçoit un email avec un bouton d'activation.
            </p>
          </div>
          <button className="au-drawer-close" onClick={() => setDrawerOpen(false)}>
            <X size={20} />
          </button>
        </div>

        {error && <div className="alert alert-error" style={{ margin: "0 0 16px" }}>{error}</div>}
        {message && <div className="alert alert-success" style={{ margin: "0 0 16px" }}>{message}</div>}

        {isAdmin && (
          <div className="alert alert-info" style={{ margin: "0 0 16px", fontSize: 13 }}>
            En tant qu'administrateur, vous gérez uniquement les utilisateurs de votre département.
          </div>
        )}

        <form className="au-drawer-form" onSubmit={createUser}>
          <div className="au-field">
            <label className="au-label">Email</label>
            <input
              className="au-input"
              type="email"
              value={form.email}
              onChange={(e) => updateField("email", e.target.value)}
              placeholder="utilisateur@tunisietelecom.tn"
              required
            />
          </div>

          <div className="au-field">
            <label className="au-label">Nom complet</label>
            <input
              className="au-input"
              value={form.nom_complet}
              onChange={(e) => updateField("nom_complet", e.target.value)}
              placeholder="Prénom Nom"
              required
            />
          </div>

          <div className="au-field">
            <label className="au-label">Département</label>
            {isSuperAdmin ? (
              <select
                className="au-input"
                value={form.departement_nom}
                onChange={(e) => updateField("departement_nom", e.target.value)}
                required
              >
                <option value="" disabled>Choisir un département</option>
                {departements.map((item) => (
                  <option key={item.id} value={item.nom_departement}>{item.nom_departement}</option>
                ))}
              </select>
            ) : (
              <div className="au-input au-input-readonly">
                {currentUser?.departement_nom || "Département associé à votre compte"}
              </div>
            )}
          </div>

          <div className="au-field">
            <label className="au-label">Rôle</label>
            {isSuperAdmin ? (
              <select
                className="au-input"
                value={form.role}
                onChange={(e) => updateField("role", e.target.value)}
              >
                <option value="USER">USER</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            ) : (
              <div className="au-input au-input-readonly">USER</div>
            )}
          </div>

          <button
            className="au-btn-submit"
            type="submit"
            disabled={loading || (isSuperAdmin && !form.departement_nom)}
          >
            <Plus size={18} />
            {loading ? "Création en cours..." : "Créer l'utilisateur"}
          </button>
        </form>
      </div>
    </Layout>
  );
}

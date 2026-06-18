import { useEffect, useMemo, useState } from "react";
import {
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  EllipsisVertical,
  FilterX,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserCheck,
  Users,
  UserX,
} from "lucide-react";
import Layout from "../components/Layout";
import PageHeader from "../components/PageHeader";
import Drawer from "../components/Drawer";
import { useAuth } from "../context/AuthContext";
import { api, getApiError } from "../api/api";

const DEFAULT_ITEMS_PER_PAGE = 10;

const ROLE_LABELS = {
  SUPER_ADMIN: "SUPER ADMIN",
  ADMIN: "ADMIN",
  USER: "USER",
};

function normalizeStatus(item) {
  if (item.date_suppression) return "SUPPRIME";
  const raw = String(item.statut_compte || "").toUpperCase();
  if (raw === "ACTIVE") return "ACTIF";
  if (raw === "PENDING_ACTIVATION" || raw === "MFA_SETUP_REQUIRED") return "EN_ATTENTE_PREMIERE_CONNEXION";
  if (raw === "DISABLED") return "DESACTIVE_ADMIN";
  return raw;
}

function roleClass(role) {
  return String(role || "USER").toLowerCase().replaceAll("_", "");
}


function formatDate(value) {
  if (!value) return "Jamais";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Jamais";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function getInitials(name, email) {
  const source = name?.trim() || email?.split("@")[0] || "U";
  const parts = source.split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : source.slice(0, 2)).toUpperCase();
}

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const isSuperAdmin = currentUser?.role === "SUPER_ADMIN";

  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [form, setForm] = useState({
    email: "",
    nom_complet: "",
    role: "USER",
    departement_nom: "",
  });
  const [message, setMessage] = useState("");
  const [debugLink, setDebugLink] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [page, setPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(DEFAULT_ITEMS_PER_PAGE);
  const [selectedIds, setSelectedIds] = useState(new Set());

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      if (isSuperAdmin) {
        const [usersResponse, departmentsResponse] = await Promise.all([
          api.get("/admin/users"),
          api.get("/admin/departements"),
        ]);
        const availableDepartments = Array.isArray(departmentsResponse.data) ? departmentsResponse.data : [];
        setUsers(usersResponse.data);
        setDepartments(availableDepartments);
        setForm((current) => ({
          ...current,
          departement_nom:
            current.departement_nom && availableDepartments.some((department) => department.nom_departement === current.departement_nom)
              ? current.departement_nom
              : availableDepartments[0]?.nom_departement || "",
        }));
      } else {
        const usersResponse = await api.get("/admin/users");
        setUsers(usersResponse.data);
        setDepartments([]);
        setForm((current) => ({ ...current, departement_nom: currentUser?.departement_nom || "", role: "USER" }));
      }
    } catch (err) {
      setError(getApiError(err, "Erreur chargement utilisateurs."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Initial synchronization with the administration API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperAdmin, currentUser?.departement_nom]);

  const createUser = async (event) => {
    event.preventDefault();
    setMessage("");
    setDebugLink("");
    setError("");
    setLoading(true);
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
      setForm((current) => ({ ...current, email: "", nom_complet: "", role: "USER" }));
      await loadData();
      setDrawerOpen(false);
    } catch (err) {
      setError(getApiError(err, "Erreur création utilisateur."));
    } finally {
      setLoading(false);
    }
  };

  const toggleStatus = async (item) => {
    const action = item.est_actif ? "désactiver" : "réactiver";
    if (!window.confirm(`Voulez-vous ${action} le compte ${item.email} ?`)) return;
    setError(""); setMessage("");
    try {
      const response = await api.patch(`/admin/users/by-email/${encodeURIComponent(item.email)}/status`, {
        est_actif: !item.est_actif,
      });
      setMessage(response.data.message || "Statut utilisateur mis à jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour statut."));
    }
  };

  const updateUserProfile = async (item, changes) => {
    if (!isSuperAdmin) return;
    setError(""); setMessage("");
    try {
      await api.patch(`/admin/users/by-email/${encodeURIComponent(item.email)}/profile`, {
        role: changes.role || item.role,
        departement_nom: changes.departement_nom || item.departement_nom || departments[0]?.nom_departement || "",
      });
      setMessage("Profil utilisateur mis à jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise à jour profil utilisateur."));
    }
  };

  const deleteUser = async (item) => {
    if (!window.confirm(`Supprimer définitivement ${item.email} ?`)) return;
    setError("");
    try {
      await api.delete(`/admin/users/by-email/${encodeURIComponent(item.email)}`);
      setMessage("Utilisateur supprimé.");
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression utilisateur."));
    }
  };

  const regenerateRecoveryCodes = async (item) => {
    if (!window.confirm(`Régénérer les codes de secours de ${item.email} et les envoyer par email ?`)) return;
    setError(""); setMessage("");
    try {
      const response = await api.post(`/admin/users/by-email/${encodeURIComponent(item.email)}/recovery-codes/regenerate`);
      setMessage(response.data.message || "Codes de secours régénérés.");
    } catch (err) {
      setError(getApiError(err, "Erreur régénération codes de secours."));
    }
  };

  const canDeactivate = (item) => item.est_actif && normalizeStatus(item) === "ACTIF" && item.id !== currentUser?.id;
  const canReactivate = (item) => !item.est_actif && ["DESACTIVE_ADMIN", "BLOQUE_TENTATIVES"].includes(normalizeStatus(item));

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return users.filter((item) => {
      const matchesSearch =
        !query ||
        item.email?.toLowerCase().includes(query) ||
        item.nom_complet?.toLowerCase().includes(query) ||
        ROLE_LABELS[item.role]?.toLowerCase().includes(query) ||
        item.role?.toLowerCase().includes(query);
      const matchesDept = !filterDept || item.departement_nom === filterDept;
      const matchesRole = !filterRole || item.role === filterRole;
      const matchesStatus = !filterStatus || String(item.est_actif) === filterStatus;
      return matchesSearch && matchesDept && matchesRole && matchesStatus;
    });
  }, [users, search, filterDept, filterRole, filterStatus]);

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / itemsPerPage));
  const currentPage = Math.min(page, totalPages);
  const paginatedUsers = filteredUsers.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);
  const visiblePages = Array.from({ length: Math.min(5, totalPages) }, (_, index) => {
    const start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
    return start + index;
  });

  const stats = useMemo(() => {
    const departmentNames = new Set(users.map((item) => item.departement_nom).filter(Boolean));
    return {
      total: users.length,
      active: users.filter((item) => item.est_actif).length,
      inactive: users.filter((item) => !item.est_actif).length,
      departments: departmentNames.size,
    };
  }, [users]);


  const resetFilters = () => {
    setSearch("");
    setFilterDept("");
    setFilterRole("");
    setFilterStatus("");
    setPage(1);
  };

  const setFilter = (setter, value) => {
    setter(value);
    setPage(1);
  };

  const toggleSelected = (id) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const allPageSelected = paginatedUsers.length > 0 && paginatedUsers.every((item) => selectedIds.has(item.id));
  const togglePageSelection = () => {
    setSelectedIds((current) => {
      const next = new Set(current);
      paginatedUsers.forEach((item) => (allPageSelected ? next.delete(item.id) : next.add(item.id)));
      return next;
    });
  };

  return (
    <Layout>
      <main className="users-admin-page">
        <PageHeader
          eyebrow="Administration"
          title="Gestion des utilisateurs"
          subtitle="Gérez les comptes, rôles et accès de votre équipe."
          action={<button className="users-create-button" onClick={() => setDrawerOpen(true)}><Plus size={18} /> Créer un utilisateur</button>}
        />

        {message && <div className="au-alert au-alert-success">{message}</div>}
        {debugLink && <div className="au-alert au-alert-debug">Lien activation debug : <a href={debugLink}>{debugLink}</a></div>}
        {error && <div className="au-alert au-alert-error">{error}</div>}

        <section className="users-kpi-grid" aria-label="Statistiques utilisateurs">
          <article className="users-kpi-card users-kpi-total">
            <span className="users-kpi-icon"><Users size={21} /></span>
            <div><strong>{stats.total}</strong><span>Total utilisateurs</span></div>
          </article>
          <article className="users-kpi-card users-kpi-active">
            <span className="users-kpi-icon"><UserCheck size={21} /></span>
            <div><strong>{stats.active}</strong><span>Comptes actifs</span></div>
          </article>
          <article className="users-kpi-card users-kpi-inactive">
            <span className="users-kpi-icon"><UserX size={21} /></span>
            <div><strong>{stats.inactive}</strong><span>Comptes inactifs</span></div>
          </article>
          <article className="users-kpi-card users-kpi-departments">
            <span className="users-kpi-icon"><Building2 size={21} /></span>
            <div><strong>{stats.departments}</strong><span>Départements couverts</span></div>
          </article>
        </section>

        <section className="users-control-panel" aria-label="Recherche et filtres">
          <div className="users-search-field">
            <Search size={18} />
            <input
              value={search}
              onChange={(event) => setFilter(setSearch, event.target.value)}
              placeholder="Rechercher par nom, email ou rôle…"
            />
          </div>
          <div className="users-filter-group">
            <select value={filterDept} onChange={(event) => setFilter(setFilterDept, event.target.value)}>
              <option value="">Tous les départements</option>
              {departments.map((department) => (
                <option key={department.id} value={department.nom_departement}>
                  {department.nom_departement}
                </option>
              ))}
            </select>
            <select value={filterRole} onChange={(event) => setFilter(setFilterRole, event.target.value)}>
              <option value="">Tous les rôles</option>
              <option value="SUPER_ADMIN">Super admin</option>
              <option value="ADMIN">Admin</option>
              <option value="USER">Utilisateur</option>
            </select>
            <select value={filterStatus} onChange={(event) => setFilter(setFilterStatus, event.target.value)}>
              <option value="">Tous les statuts</option>
              <option value="true">Actifs</option>
              <option value="false">Inactifs</option>
            </select>
            <button className="users-reset-button" onClick={resetFilters} title="Réinitialiser les filtres">
              <FilterX size={17} /><span>Réinitialiser</span>
            </button>
            <button className="users-refresh-button" onClick={loadData} title="Actualiser">
              <RefreshCw size={17} />
            </button>
          </div>
          <div className="users-results-meta">
            <strong>{filteredUsers.length}</strong> utilisateur{filteredUsers.length > 1 ? "s" : ""} trouvé{filteredUsers.length > 1 ? "s" : ""}
            {selectedIds.size > 0 && <span>{selectedIds.size} sélectionné{selectedIds.size > 1 ? "s" : ""}</span>}
          </div>
        </section>

        <section className="users-table-shell">
          <div className="users-table-scroll">
            <table className="users-premium-table">
              <thead>
                <tr>
                  <th className="users-check-column">
                    <input type="checkbox" checked={allPageSelected} onChange={togglePageSelection} aria-label="Sélectionner la page" />
                  </th>
                  <th>Utilisateur</th>
                  <th>Rôle</th>
                  <th>Département</th>
                  <th>Statut</th>
                  <th>Dernière connexion</th>
                  <th className="users-actions-heading">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="7" className="users-table-state">Chargement des utilisateurs…</td></tr>
                ) : paginatedUsers.length === 0 ? (
                  <tr><td colSpan="7" className="users-table-state">Aucun utilisateur ne correspond aux filtres.</td></tr>
                ) : paginatedUsers.map((item) => (
                  <tr key={item.id} className={selectedIds.has(item.id) ? "is-selected" : ""}>
                    <td className="users-check-column">
                      <input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggleSelected(item.id)} aria-label={`Sélectionner ${item.email}`} />
                    </td>
                    <td>
                      <div className="users-person-cell">
                        <span className="users-avatar">{getInitials(item.nom_complet, item.email)}</span>
                        <div><strong>{item.nom_complet || "Nom non renseigné"}</strong><span>{item.email}</span></div>
                      </div>
                    </td>
                    <td>
                      {isSuperAdmin ? (
                        <select
                          className="users-inline-access-select"
                          value={item.role}
                          aria-label={`Rôle de ${item.email}`}
                          onChange={(event) => updateUserProfile(item, { role: event.target.value })}
                        >
                          <option value="SUPER_ADMIN">Super admin</option>
                          <option value="ADMIN">Admin</option>
                          <option value="USER">Utilisateur</option>
                        </select>
                      ) : (
                        <span className={`users-role-badge role-${roleClass(item.role)}`}>{ROLE_LABELS[item.role] || item.role}</span>
                      )}
                    </td>
                     <td>
                      {isSuperAdmin ? (
                        <select
                          className="users-inline-access-select users-inline-department-select"
                          value={item.departement_nom || ""}
                          aria-label={`Département de ${item.email}`}
                          onChange={(event) => {
                            const val = event.target.value;
                            // Seul SUPER_ADMIN peut avoir un département vide
                            if (!val && item.role !== "SUPER_ADMIN") return;
                            updateUserProfile(item, { departement_nom: val || null });
                          }}
                        >
                          {item.role === "SUPER_ADMIN" && <option value="">Aucun</option>}
                          {departments.map((department) => (
                            <option key={department.id} value={department.nom_departement}>
                              {department.nom_departement}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="users-department-tag">{item.departement_nom || "Aucun"}</span>
                      )}
                    </td>
                    <td>
                      {(() => {
                        const st = normalizeStatus(item);
                        const statusConfig = {
                          ACTIF: { cls: "is-active", label: "Actif" },
                          EN_ATTENTE_PREMIERE_CONNEXION: { cls: "is-pending", label: "En attente" },
                          DESACTIVE_ADMIN: { cls: "is-inactive", label: "Désactivé" },
                          BLOQUE_TENTATIVES: { cls: "is-blocked", label: "Bloqué" },
                          SUPPRIME: { cls: "is-deleted", label: "Supprimé" },
                        };
                        const cfg = statusConfig[st] || { cls: "is-inactive", label: st };
                        return (
                          <span className={`users-status-badge ${cfg.cls}`}>
                            <i />{cfg.label}
                          </span>
                        );
                      })()}
                    </td>
                    <td><span className="users-last-login">{formatDate(item.date_derniere_connexion)}</span></td>
                    <td className="users-actions-cell">
                      <details className="users-action-dropdown">
                        <summary aria-label={`Actions pour ${item.email}`}><EllipsisVertical size={19} /></summary>
                        <div className="users-action-menu">
                          <button onClick={() => regenerateRecoveryCodes(item)}><KeyRound size={15} /> Codes de secours</button>
                          {canDeactivate(item) && (
                            <button onClick={() => toggleStatus(item)}><UserX size={15} /> Désactiver</button>
                          )}
                          {canReactivate(item) && (
                            <button onClick={() => toggleStatus(item)}><CheckCircle2 size={15} /> Réactiver</button>
                          )}
                          <button className="is-danger" onClick={() => deleteUser(item)}><Trash2 size={15} /> Supprimer</button>
                        </div>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <footer className="users-pagination">
            <div className="users-per-page">
              <span>Afficher</span>
              <select value={itemsPerPage} onChange={(event) => { setItemsPerPage(Number(event.target.value)); setPage(1); }}>
                <option value="10">10</option>
                <option value="25">25</option>
                <option value="50">50</option>
              </select>
              <span>par page</span>
            </div>
            <span className="users-range">
              {filteredUsers.length ? (currentPage - 1) * itemsPerPage + 1 : 0} - {Math.min(currentPage * itemsPerPage, filteredUsers.length)} sur {filteredUsers.length}
            </span>
            <nav aria-label="Pagination utilisateurs">
              <button disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} /></button>
              {visiblePages.map((pageNumber) => (
                <button key={pageNumber} className={pageNumber === currentPage ? "is-current" : ""} onClick={() => setPage(pageNumber)}>{pageNumber}</button>
              ))}
              <button disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} /></button>
            </nav>
          </footer>
        </section>
      </main>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Créer un utilisateur"
        description="Après création, l’utilisateur reçoit un email avec un bouton d’activation."
        labelledBy="create-user-title"
        footer={(
          <button type="submit" form="create-user-form" className="au-btn-submit" disabled={loading || (isSuperAdmin && !form.departement_nom)}>
            <Plus size={16} /> {loading ? "Création en cours…" : "Créer l’utilisateur"}
          </button>
        )}
      >
        <form id="create-user-form" onSubmit={createUser} className="platform-drawer-form">
          <div className="au-field">
            <label className="au-label">Nom complet</label>
            <input className="au-input" value={form.nom_complet} onChange={(event) => setForm({ ...form, nom_complet: event.target.value })} required />
          </div>
          <div className="au-field">
            <label className="au-label">Email</label>
            <input className="au-input" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          </div>
          <div className="au-field">
            <label className="au-label">Rôle</label>
            {isSuperAdmin ? (
              <select className="au-input" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
                <option value="USER">Utilisateur</option>
                <option value="ADMIN">Admin</option>
              </select>
            ) : (
              <div className="au-input au-input-readonly">USER</div>
            )}
          </div>
          <div className="au-field">
            <label className="au-label">Département</label>
            {isSuperAdmin ? (
              <select className="au-input" value={form.departement_nom} onChange={(event) => setForm({ ...form, departement_nom: event.target.value })} required>
                {departments.map((department) => (
                  <option key={department.id} value={department.nom_departement}>
                    {department.nom_departement}
                  </option>
                ))}
              </select>
            ) : (
              <div className="au-input au-input-readonly">{currentUser?.departement_nom || "Département associé à votre compte"}</div>
            )}
          </div>
        </form>
      </Drawer>
    </Layout>
  );
}

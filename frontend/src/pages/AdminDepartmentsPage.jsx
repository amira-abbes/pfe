import { Building2, Key, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, getApiError } from "../api/api";
import { DEPARTMENT_KEYS, departmentKey } from "../accessControl";
import Layout from "../components/Layout";

const ITEMS_PER_PAGE = 10;

const PERMISSION_LABELS = {
  voir_dashboard_service_sos: "Dashboard Service SOS",
  voir_dashboard_parc_service_sos: "Dashboard Parc Service SOS",
  voir_dashboard_bad_debts: "Dashboard Bad Debts",
  lancer_traitement_elt: "Lancer traitement ELT",
  voir_resultat_elt: "Voir résultat ELT",
};

const VALID_PERMISSION_NAMES = Object.keys(PERMISSION_LABELS);

const DEPARTMENT_ALLOWED_PERMISSIONS = {
  [DEPARTMENT_KEYS.COMMERCIAL]: ["voir_dashboard_bad_debts"],
  [DEPARTMENT_KEYS.ASSURANCE_RISQUE]: [
    "voir_dashboard_service_sos",
    "voir_dashboard_parc_service_sos",
    "lancer_traitement_elt",
    "voir_resultat_elt",
  ],
  [DEPARTMENT_KEYS.ANALYSE_OPERATIONNELLE]: [
    "voir_dashboard_service_sos",
    "voir_dashboard_parc_service_sos",
    "lancer_traitement_elt",
    "voir_resultat_elt",
  ],
};

function permissionLabel(permission) {
  return permission?.label || PERMISSION_LABELS[permission?.nom_droit] || permission?.nom_droit;
}

export default function AdminDepartmentsPage() {
  // ── Core state (unchanged logic) ──────────────────────────────────────────
  const [departements, setDepartements] = useState([]);
  const [droits, setDroits] = useState([]);
  const [selectedDepartement, setSelectedDepartement] = useState("");
  const [selectedDroits, setSelectedDroits] = useState([]);
  const [droitToAdd, setDroitToAdd] = useState("");
  const [newDepartement, setNewDepartement] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [rightsError, setRightsError] = useState("");
  const [loadingRights, setLoadingRights] = useState(false);

  // ── UI state ───────────────────────────────────────────────────────────────
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchDept, setSearchDept] = useState("");
  const [page, setPage] = useState(1);

  const allowedPermissionNames = useMemo(() => {
    const key = departmentKey(selectedDepartement);
    return DEPARTMENT_ALLOWED_PERMISSIONS[key] || [];
  }, [selectedDepartement]);

  const availableDroits = useMemo(
    () =>
      droits.filter(
        (droit) =>
          VALID_PERMISSION_NAMES.includes(droit.nom_droit) &&
          allowedPermissionNames.includes(droit.nom_droit) &&
          !selectedDroits.some((item) => item.nom_droit === droit.nom_droit)
      ),
    [droits, selectedDroits, allowedPermissionNames]
  );

  async function loadData() {
    setError("");
    setRightsError("");

    try {
      const [depsResponse, droitsResponse] = await Promise.all([
        api.get("/admin/departements"),
        api.get("/admin/droits"),
      ]);

      const deps = Array.isArray(depsResponse.data) ? depsResponse.data : [];
      const allDroits = Array.isArray(droitsResponse.data)
        ? droitsResponse.data.filter((droit) => VALID_PERMISSION_NAMES.includes(droit.nom_droit))
        : [];

      setDepartements(deps);
      setDroits(allDroits);

      if (selectedDepartement && !deps.some((item) => item.nom_departement === selectedDepartement)) {
        setSelectedDepartement("");
        setSelectedDroits([]);
        setDroitToAdd("");
      }
    } catch (err) {
      setError(getApiError(err, "Erreur chargement départements/permissions."));
    }
  }

  async function loadDepartmentRights(nom) {
    setRightsError("");
    setSelectedDroits([]);
    setDroitToAdd("");

    if (!nom) return;

    setLoadingRights(true);

    try {
      const response = await api.get(
        `/admin/departements/by-name/${encodeURIComponent(nom)}/droits`
      );
      setSelectedDroits(
        (response.data?.droits || []).filter((droit) =>
          VALID_PERMISSION_NAMES.includes(droit.nom_droit)
        )
      );
    } catch (err) {
      setSelectedDroits([]);
      setRightsError(getApiError(err, "Département introuvable ou supprimé."));
    } finally {
      setLoadingRights(false);
    }
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createDepartement(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setRightsError("");

    try {
      const response = await api.post("/admin/departements", {
        nom_departement: newDepartement,
      });

      const createdName = response.data?.nom_departement;

      setMessage("Département créé avec succès.");
      setNewDepartement("");
      setDrawerOpen(false);

      await loadData();

      if (createdName) {
        setSelectedDepartement(createdName);
        await loadDepartmentRights(createdName);
      }
    } catch (err) {
      setError(getApiError(err, "Erreur création département."));
    }
  }

  async function deleteDepartement(nom) {
    if (!confirm(`Supprimer le département ${nom} ?`)) return;

    setError("");
    setMessage("");
    setRightsError("");

    try {
      await api.delete(`/admin/departements/by-name/${encodeURIComponent(nom)}`);

      setMessage("Département supprimé avec succès.");

      setDepartements((prev) => prev.filter((item) => item.nom_departement !== nom));

      if (selectedDepartement === nom) {
        setSelectedDepartement("");
        setSelectedDroits([]);
        setDroitToAdd("");
      }

      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression département."));
    }
  }

  async function addPermission(event) {
    event.preventDefault();

    if (!selectedDepartement || !droitToAdd) return;

    setError("");
    setMessage("");
    setRightsError("");

    try {
      await api.post(
        `/admin/departements/by-name/${encodeURIComponent(
          selectedDepartement
        )}/droits/${encodeURIComponent(droitToAdd)}`
      );

      setMessage("Permission accordée au département.");
      await loadDepartmentRights(selectedDepartement);
    } catch (err) {
      setRightsError(getApiError(err, "Erreur ajout permission."));
    }
  }

  async function removePermission(nomDroit) {
    if (!selectedDepartement || !nomDroit) return;

    setError("");
    setMessage("");
    setRightsError("");

    try {
      await api.delete(
        `/admin/departements/by-name/${encodeURIComponent(
          selectedDepartement
        )}/droits/${encodeURIComponent(nomDroit)}`
      );

      setMessage("Permission retirée du département.");
      await loadDepartmentRights(selectedDepartement);
    } catch (err) {
      setRightsError(getApiError(err, "Erreur retrait permission."));
    }
  }

  // ── Derived / filtered data ────────────────────────────────────────────────
  const filteredDepts = useMemo(() => {
    if (!searchDept) return departements;
    const q = searchDept.toLowerCase();
    return departements.filter((d) => d.nom_departement.toLowerCase().includes(q));
  }, [departements, searchDept]);

  const totalPages = Math.max(1, Math.ceil(filteredDepts.length / ITEMS_PER_PAGE));
  const paginatedDepts = filteredDepts.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  return (
    <Layout>
      {/* ── Page header ────────────────────────────────────────────────── */}
      <div className="au-page-header">
        <div>
          <h1 className="au-page-title">Départements & permissions</h1>
          <p className="au-page-sub">Gérez la structure organisationnelle et les accès au système.</p>
        </div>
        <button className="au-btn-create" onClick={() => { setDrawerOpen(true); setMessage(""); setError(""); }}>
          <Plus size={18} />
          Créer un département
        </button>
      </div>

      {/* ── Global alerts ──────────────────────────────────────────────── */}
      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
      {message && <div className="alert alert-success" style={{ marginBottom: 16 }}>{message}</div>}

      {/* ── Stats cards ────────────────────────────────────────────────── */}
      {/* ── Stats cards ────────────────────────────────────────────────── */}
      <div className="au-stats-row">
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#eff6ff", color: "#2563eb" }}>
            <Building2 size={26} />
          </div>
          <div>
            <div className="au-stat-value">{departements.length}</div>
            <div className="au-stat-label">Départements</div>
          </div>
        </div>
        <div className="au-stat-card">
          <div className="au-stat-icon" style={{ background: "#fdf4ff", color: "#c026d3" }}>
            <Key size={26} />
          </div>
          <div>
            <div className="au-stat-value">{droits.length}</div>
            <div className="au-stat-label">Permissions métier disponibles</div>
          </div>
        </div>
      </div>

      {/* ── Search & filters ───────────────────────────────────────────── */}
      <div className="au-filter-bar">
        <div className="au-search-wrap">
          <Search size={16} className="au-search-icon" />
          <input
            className="au-search-input"
            placeholder="Rechercher un département..."
            value={searchDept}
            onChange={(e) => { setSearchDept(e.target.value); setPage(1); }}
          />
        </div>
        <button className="au-refresh-btn" onClick={loadData} title="Actualiser">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* ── Table ─────────────────────────────────────────────────────── */}
      <div className="au-table-card">
        <div className="au-table-wrap">
          <table className="au-table">
            <thead>
              <tr>
                <th>Nom du département</th>
                <th style={{ width: 150 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedDepts.map((item) => (
                <tr key={item.id} className="au-table-row">
                  <td className="au-td-name" style={{ fontWeight: 600, color: "#0f172a" }}>
                    {item.nom_departement}
                  </td>
                  <td>
                    <button className="au-btn-delete" onClick={() => deleteDepartement(item.nom_departement)}>
                      <Trash2 size={14} />
                      Supprimer
                    </button>
                  </td>
                </tr>
              ))}
              {paginatedDepts.length === 0 && (
                <tr>
                  <td colSpan="2" className="au-empty-row">
                    {searchDept ? "Aucun département ne correspond à votre recherche." : "Aucun département."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* ── Mobile card list ── */}
        <div className="au-card-list">
          {paginatedDepts.map((item) => (
            <div key={item.id} className="au-list-card">
              <div className="au-list-card-header">
                <div className="au-td-name" style={{ fontWeight: 600, color: "#0f172a" }}>
                  {item.nom_departement}
                </div>
              </div>
              <div className="au-list-card-actions">
                <button className="au-btn-delete" onClick={() => deleteDepartement(item.nom_departement)}>
                  <Trash2 size={14} />
                  Supprimer
                </button>
              </div>
            </div>
          ))}
          {paginatedDepts.length === 0 && (
            <div className="au-empty-row">
              {searchDept ? "Aucun département ne correspond à votre recherche." : "Aucun département."}
            </div>
          )}
        </div>

        {/* Pagination */}
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

      {/* ── Permissions Management ─────────────────────────────────────── */}
      <div className="au-table-card" style={{ padding: "24px" }}>
        <h2 className="au-page-title" style={{ fontSize: "18px", marginBottom: "20px" }}>Permissions du département</h2>
        
        <div className="au-field" style={{ marginBottom: "20px", maxWidth: "400px" }}>
          <label className="au-label">Sélectionner un département</label>
          <select
            className="au-input"
            value={selectedDepartement}
            onChange={async (event) => {
              const next = event.target.value;
              setSelectedDepartement(next);
              await loadDepartmentRights(next);
            }}
          >
            <option value="">-- Choisir un département --</option>
            {departements.map((item) => (
              <option key={item.id} value={item.nom_departement}>
                {item.nom_departement}
              </option>
            ))}
          </select>
        </div>

        {!selectedDepartement && (
          <div className="alert alert-info">
            Sélectionnez un département pour afficher et gérer ses permissions.
          </div>
        )}

        {rightsError && (
          <div className="alert alert-error" style={{ marginBottom: "16px" }}>{rightsError}</div>
        )}

        {selectedDepartement && (
          <>
            <form onSubmit={addPermission} style={{ display: "flex", gap: "10px", marginBottom: "24px", maxWidth: "600px" }}>
              <select
                className="au-input"
                style={{ flex: 1 }}
                value={droitToAdd}
                onChange={(event) => setDroitToAdd(event.target.value)}
                disabled={!availableDroits.length || loadingRights}
              >
                <option value="">Choisir une permission à ajouter...</option>
                {availableDroits.map((droit) => (
                  <option key={droit.id} value={droit.nom_droit}>
                    {permissionLabel(droit)}
                  </option>
                ))}
              </select>
              <button
                className="au-btn-create"
                disabled={!droitToAdd || loadingRights}
                type="submit"
                style={{ margin: 0, background: "#10b981", boxShadow: "0 4px 16px rgba(16,185,129,0.25)" }}
              >
                <Plus size={18} />
                Accorder
              </button>
            </form>

            <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
              {selectedDroits.map((droit) => (
                <div
                  key={droit.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    padding: "8px 14px",
                    borderRadius: "12px",
                    fontSize: "13px",
                    fontWeight: "600",
                    color: "#374151"
                  }}
                >
                  <Key size={14} style={{ color: "#94a3b8" }} />
                  {permissionLabel(droit)}
                  <button
                    type="button"
                    onClick={() => removePermission(droit.nom_droit)}
                    title="Retirer la permission"
                    style={{
                      background: "none",
                      border: "none",
                      color: "#ef4444",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      padding: "2px",
                      marginLeft: "4px",
                      transition: "transform 0.15s"
                    }}
                    onMouseOver={(e) => e.currentTarget.style.transform = "scale(1.2)"}
                    onMouseOut={(e) => e.currentTarget.style.transform = "scale(1)"}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}

              {!loadingRights && selectedDepartement && selectedDroits.length === 0 && !rightsError && (
                <div className="alert alert-info" style={{ width: "100%" }}>
                  Aucune permission n'a été accordée à ce département.
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Drawer Overlay ────────────────────────────────────────────── */}
      {drawerOpen && (
        <div className="au-overlay" onClick={() => setDrawerOpen(false)} />
      )}

      {/* ── Drawer Panel ──────────────────────────────────────────────── */}
      <div className={`au-drawer ${drawerOpen ? "au-drawer-open" : ""}`}>
        <div className="au-drawer-header">
          <div>
            <h2 className="au-drawer-title">Créer un département</h2>
            <p className="au-drawer-hint">
              Ajoutez un nouveau département pour organiser vos équipes.
            </p>
          </div>
          <button className="au-drawer-close" onClick={() => setDrawerOpen(false)}>
            <X size={20} />
          </button>
        </div>

        <form className="au-drawer-form" onSubmit={createDepartement}>
          <div className="au-field">
            <label className="au-label">Nom du département</label>
            <input
              className="au-input"
              value={newDepartement}
              onChange={(event) => setNewDepartement(event.target.value)}
              placeholder="ex: Technique, Marketing..."
              required
            />
          </div>

          <button className="au-btn-submit" type="submit">
            <Plus size={18} />
            Créer le département
          </button>
        </form>
      </div>
    </Layout>
  );
}

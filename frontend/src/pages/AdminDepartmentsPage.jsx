import {
  BarChart3,
  Building2,
  EllipsisVertical,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  TrendingDown,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, getApiError } from "../api/api";
import { DEPARTMENT_KEYS, departmentKey } from "../accessControl";
import Layout from "../components/Layout";
import PageHeader from "../components/PageHeader";
import Drawer from "../components/Drawer";

const PERMISSIONS = {
  voir_dashboard_service_sos: {
    label: "Dashboard Service SOS",
    description: "Accès aux indicateurs opérationnels du service SOS.",
    icon: BarChart3,
  },
  voir_dashboard_parc_service_sos: {
    label: "Dashboard Parc Service SOS",
    description: "Analyse de l’évolution du parc abonné et des services SOS.",
    icon: BarChart3,
  },
  voir_dashboard_bad_debts: {
    label: "Dashboard Bad Debts",
    description: "Consultation des risques de mauvaises créances et prédictions IA.",
    icon: TrendingDown,
  },
  lancer_traitement_elt: {
    label: "Traitement ELT",
    description: "Lancement et supervision des traitements de données.",
    icon: Workflow,
  },
  voir_resultat_elt: {
    label: "Résultats ELT",
    description: "Consultation des résultats et contrôles de traitement.",
    icon: ShieldCheck,
  },
};

const VALID_PERMISSION_NAMES = Object.keys(PERMISSIONS);

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

function DepartmentActionMenu({ departmentName, onDelete }) {
  const buttonRef = useRef(null);
  const menuRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open) return undefined;

    function updatePosition() {
      const trigger = buttonRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      const viewportPadding = 10;
      const gap = 6;
      const menuWidth = 150;
      const menuHeight = menuRef.current?.offsetHeight || 46;
      const left = Math.min(
        Math.max(viewportPadding, rect.right - menuWidth),
        window.innerWidth - menuWidth - viewportPadding
      );
      const spaceBelow = window.innerHeight - rect.bottom;
      const top = spaceBelow >= menuHeight + gap + viewportPadding
        ? rect.bottom + gap
        : Math.max(viewportPadding, rect.top - menuHeight - gap);

      setPosition({ top, left });
    }

    function handlePointerDown(event) {
      if (buttonRef.current?.contains(event.target) || menuRef.current?.contains(event.target)) return;
      setOpen(false);
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") setOpen(false);
    }

    updatePosition();
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  function handleDelete() {
    setOpen(false);
    onDelete(departmentName);
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={`governance-row-menu-trigger ${open ? "is-open" : ""}`}
        aria-label={`Actions pour ${departmentName}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <EllipsisVertical size={18} />
      </button>
      {open && createPortal(
        <div
          ref={menuRef}
          className="governance-row-menu-popover"
          role="menu"
          style={{ top: position.top, left: position.left }}
        >
          <button type="button" className="danger" role="menuitem" onClick={handleDelete}>
            <Trash2 size={15} />
            Supprimer
          </button>
        </div>,
        document.body
      )}
    </>
  );
}

export default function AdminDepartmentsPage() {
  const [departements, setDepartements] = useState([]);
  const [droits, setDroits] = useState([]);
  const [selectedDepartement, setSelectedDepartement] = useState("");
  const [selectedDroits, setSelectedDroits] = useState([]);
  const [newDepartement, setNewDepartement] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [rightsError, setRightsError] = useState("");
  const [loadingRights, setLoadingRights] = useState(false);
  const [updatingPermission, setUpdatingPermission] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchDept, setSearchDept] = useState("");

  const allowedPermissionNames = useMemo(
    () => DEPARTMENT_ALLOWED_PERMISSIONS[departmentKey(selectedDepartement)] || [],
    [selectedDepartement]
  );

  const displayedPermissions = useMemo(
    () => droits.filter((droit) => allowedPermissionNames.includes(droit.nom_droit)),
    [droits, allowedPermissionNames]
  );

  const selectedPermissionNames = useMemo(
    () => new Set(selectedDroits.map((droit) => droit.nom_droit)),
    [selectedDroits]
  );

  const filteredDepts = useMemo(() => {
    const query = searchDept.trim().toLowerCase();
    return query
      ? departements.filter((department) => department.nom_departement.toLowerCase().includes(query))
      : departements;
  }, [departements, searchDept]);

  async function loadData() {
    setError("");
    setRightsError("");
    try {
      const [departmentsResponse, rightsResponse] = await Promise.all([
        api.get("/admin/departements"),
        api.get("/admin/droits"),
      ]);
      const departments = Array.isArray(departmentsResponse.data) ? departmentsResponse.data : [];
      const availableRights = Array.isArray(rightsResponse.data)
        ? rightsResponse.data.filter((right) => VALID_PERMISSION_NAMES.includes(right.nom_droit))
        : [];
      setDepartements(departments);
      setDroits(availableRights);
      if (selectedDepartement && !departments.some((item) => item.nom_departement === selectedDepartement)) {
        setSelectedDepartement("");
        setSelectedDroits([]);
      }
    } catch (err) {
      setError(getApiError(err, "Erreur chargement départements/permissions."));
    }
  }

  async function loadDepartmentRights(name) {
    setRightsError("");
    setSelectedDroits([]);
    if (!name) return;
    setLoadingRights(true);
    try {
      const response = await api.get(`/admin/departements/by-name/${encodeURIComponent(name)}/droits`);
      setSelectedDroits(
        (response.data?.droits || []).filter((right) => VALID_PERMISSION_NAMES.includes(right.nom_droit))
      );
    } catch (err) {
      setRightsError(getApiError(err, "Département introuvable ou supprimé."));
    } finally {
      setLoadingRights(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function selectDepartment(name) {
    setSelectedDepartement(name);
    await loadDepartmentRights(name);
  }

  async function createDepartement(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setRightsError("");
    try {
      const response = await api.post("/admin/departements", { nom_departement: newDepartement });
      const createdName = response.data?.nom_departement;
      setMessage("Département créé avec succès.");
      setNewDepartement("");
      setDrawerOpen(false);
      await loadData();
      if (createdName) await selectDepartment(createdName);
    } catch (err) {
      setError(getApiError(err, "Erreur création département."));
    }
  }

  async function deleteDepartement(name) {
    if (!window.confirm(`Supprimer le département ${name} ?`)) return;
    setError("");
    setMessage("");
    setRightsError("");
    try {
      await api.delete(`/admin/departements/by-name/${encodeURIComponent(name)}`);
      setMessage("Département supprimé avec succès.");
      setDepartements((current) => current.filter((item) => item.nom_departement !== name));
      if (selectedDepartement === name) {
        setSelectedDepartement("");
        setSelectedDroits([]);
      }
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression département."));
    }
  }

  async function togglePermission(permissionName) {
    if (!selectedDepartement || updatingPermission) return;
    const isAssigned = selectedPermissionNames.has(permissionName);
    setError("");
    setMessage("");
    setRightsError("");
    setUpdatingPermission(permissionName);
    try {
      const endpoint = `/admin/departements/by-name/${encodeURIComponent(selectedDepartement)}/droits/${encodeURIComponent(permissionName)}`;
      if (isAssigned) {
        await api.delete(endpoint);
      } else {
        await api.post(endpoint);
      }
      await loadDepartmentRights(selectedDepartement);
      setMessage("Permission mise à jour avec succès.");
      localStorage.setItem(
        "permissionsChangedAt",
        `${selectedDepartement}:${permissionName}:${isAssigned ? "revoked" : "granted"}`
      );
      window.dispatchEvent(new CustomEvent("permissions:changed", {
        detail: { departement_nom: selectedDepartement },
      }));
    } catch (err) {
      setRightsError(getApiError(err, isAssigned ? "Erreur retrait permission." : "Erreur ajout permission."));
    } finally {
      setUpdatingPermission("");
    }
  }

  return (
    <Layout>
      <div className="governance-page">
        <PageHeader
          eyebrow="Gouvernance"
          title="Départements & permissions"
          subtitle="Organisez les rôles, les accès et les périmètres métier."
          action={<button className="au-btn-create" onClick={() => { setDrawerOpen(true); setMessage(""); setError(""); }}><Plus size={18} />Créer un département</button>}
        />

        {error && <div className="alert alert-error governance-alert">{error}</div>}
        {message && <div className="alert alert-success governance-alert">{message}</div>}

        <section className="governance-kpis" aria-label="Statistiques de gouvernance">
          <article><span className="blue"><Building2 size={21} /></span><div><strong>{departements.length}</strong><small>Départements</small></div></article>
          <article><span className="violet"><KeyRound size={21} /></span><div><strong>{droits.length}</strong><small>Permissions métier disponibles</small></div></article>
          <article><span className="cyan"><ShieldCheck size={21} /></span><div><strong>{selectedDepartement ? selectedDroits.length : "—"}</strong><small>Permissions du département sélectionné</small></div></article>
        </section>

        <section className="governance-workspace">
          <aside className="governance-departments-panel">
            <div className="governance-panel-heading">
              <div><span>Organisation</span><h2>Départements</h2></div>
              <button onClick={loadData} title="Actualiser"><RefreshCw size={16} /></button>
            </div>
            <label className="governance-search">
              <Search size={17} />
              <input value={searchDept} onChange={(event) => setSearchDept(event.target.value)} placeholder="Rechercher un département…" />
            </label>
            <div className="governance-department-list">
              {filteredDepts.map((department) => {
                const isSelected = department.nom_departement === selectedDepartement;
                return (
                  <div className={`governance-department-row ${isSelected ? "is-selected" : ""}`} key={department.id}>
                    <button className="governance-department-select" onClick={() => selectDepartment(department.nom_departement)}>
                      <span className="governance-department-icon"><Building2 size={18} /></span>
                      <span><strong>{department.nom_departement}</strong><small>{isSelected ? `${selectedDroits.length} permission${selectedDroits.length > 1 ? "s" : ""}` : "Sélectionner pour gérer les accès"}</small></span>
                    </button>
                    <DepartmentActionMenu
                      departmentName={department.nom_departement}
                      onDelete={deleteDepartement}
                    />
                  </div>
                );
              })}
              {!filteredDepts.length && <div className="governance-list-empty">Aucun département ne correspond à votre recherche.</div>}
            </div>
          </aside>

          <section className="governance-permissions-panel">
            {!selectedDepartement ? (
              <div className="governance-empty-state">
                <span><ShieldCheck size={30} /></span>
                <h2>Sélectionnez un département</h2>
                <p>Les permissions associées apparaîtront ici.</p>
              </div>
            ) : (
              <>
                <div className="governance-permissions-heading">
                  <div><span>Contrôle des accès</span><h2>Permissions du département</h2><p>Sélectionnez les modules accessibles pour ce département.</p></div>
                  <strong>{selectedDepartement}</strong>
                </div>
                {rightsError && <div className="alert alert-error governance-alert">{rightsError}</div>}
                {loadingRights ? (
                  <div className="governance-permissions-loading">Chargement des permissions…</div>
                ) : (
                  <div className="governance-permission-list">
                    {displayedPermissions.map((right) => {
                      const meta = PERMISSIONS[right.nom_droit];
                      const Icon = meta.icon;
                      const isAssigned = selectedPermissionNames.has(right.nom_droit);
                      const isUpdating = updatingPermission === right.nom_droit;
                      return (
                        <article className={`governance-permission-row ${isAssigned ? "is-enabled" : ""}`} key={right.id}>
                          <span className="governance-permission-icon"><Icon size={19} /></span>
                          <div><strong>{meta.label}</strong><p>{meta.description}</p></div>
                          <button
                            className={`governance-switch ${isAssigned ? "is-on" : ""}`}
                            onClick={() => togglePermission(right.nom_droit)}
                            disabled={Boolean(updatingPermission)}
                            role="switch"
                            aria-checked={isAssigned}
                            aria-label={`${isAssigned ? "Retirer" : "Accorder"} ${meta.label}`}
                          >
                            <i />{isUpdating && <span />}
                          </button>
                        </article>
                      );
                    })}
                    {!displayedPermissions.length && (
                      <div className="governance-restricted-empty"><KeyRound size={22} /><div><strong>Aucune permission disponible</strong><p>Ce département ne possède pas de périmètre métier configurable.</p></div></div>
                    )}
                  </div>
                )}
              </>
            )}
          </section>
        </section>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Créer un département"
        description="Ajoutez un nouveau département pour organiser vos équipes."
        labelledBy="create-department-title"
        footer={<button className="au-btn-submit" type="submit" form="create-department-form"><Plus size={18} />Créer le département</button>}
      >
        <form id="create-department-form" className="platform-drawer-form" onSubmit={createDepartement}>
          <div className="au-field"><label className="au-label">Nom du département</label><input className="au-input" value={newDepartement} onChange={(event) => setNewDepartement(event.target.value)} placeholder="ex: Technique, Marketing…" required /></div>
        </form>
      </Drawer>
    </Layout>
  );
}

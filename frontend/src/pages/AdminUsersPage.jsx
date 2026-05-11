import { Plus, RefreshCw, UserCheck, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { api, getApiError } from "../api/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";

const STATUS_LABELS = {
  ACTIF: "Actif",
  EN_ATTENTE_PREMIERE_CONNEXION: "En attente de premiere connexion",
  DESACTIVE_ADMIN: "Desactive",
  BLOQUE_TENTATIVES: "Bloque",
  SUPPRIME: "Supprime",
};

const STATUS_CLASSES = {
  ACTIF: "badge badge-green",
  EN_ATTENTE_PREMIERE_CONNEXION: "badge badge-orange",
  DESACTIVE_ADMIN: "badge badge-orange",
  BLOQUE_TENTATIVES: "badge badge-red",
  SUPPRIME: "badge badge-gray",
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

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const isSuperAdmin = currentUser?.role === "SUPER_ADMIN";
  const isAdmin = currentUser?.role === "ADMIN";

  const [users, setUsers] = useState([]);
  const [departements, setDepartements] = useState([]);
  const [form, setForm] = useState({
    email: "",
    nom_complet: "",
    departement_nom: "",
  });
  const [message, setMessage] = useState("");
  const [debugLink, setDebugLink] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
        setForm((current) => ({
          ...current,
          departement_nom:
            current.departement_nom &&
            deps.some((item) => item.nom_departement === current.departement_nom)
              ? current.departement_nom
              : deps[0]?.nom_departement || "",
        }));
      } else {
        const usersResponse = await api.get("/admin/users");
        setUsers(usersResponse.data);
        setDepartements([]);
        setForm((current) => ({
          ...current,
          departement_nom: currentUser?.departement_nom || "",
        }));
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
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function createUser(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setDebugLink("");
    setLoading(true);

    try {
      const payload = {
        email: form.email,
        nom_complet: form.nom_complet,
        departement_nom: isSuperAdmin
          ? form.departement_nom
          : currentUser?.departement_nom || form.departement_nom || "",
      };

      const response = await api.post("/admin/users", payload);
      setMessage(response.data.message || "Utilisateur cree.");
      setDebugLink(response.data.activation_link_debug || "");
      setForm((current) => ({ ...current, email: "", nom_complet: "" }));
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur creation utilisateur."));
    } finally {
      setLoading(false);
    }
  }

  async function updateUserDepartment(item, departementNom) {
    if (!isSuperAdmin) return;
    setError("");
    setMessage("");

    try {
      await api.patch(`/admin/users/by-email/${encodeURIComponent(item.email)}/profile`, {
        departement_nom: departementNom,
      });
      setMessage("Departement utilisateur mis a jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise a jour departement utilisateur."));
    }
  }

  async function toggleStatus(item) {
    const action = item.est_actif ? "desactiver" : "reactiver";
    if (!confirm(`Voulez-vous ${action} le compte ${item.email} ?`)) return;

    setError("");
    setMessage("");

    try {
      const response = await api.patch(`/admin/users/by-email/${encodeURIComponent(item.email)}/status`, {
        est_actif: !item.est_actif,
      });
      setMessage(response.data.message || "Statut utilisateur mis a jour.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur mise a jour statut."));
    }
  }

  async function deleteUser(item) {
    if (!confirm(`Supprimer l'utilisateur ${item.email} ?`)) return;

    setError("");
    setMessage("");

    try {
      await api.delete(`/admin/users/by-email/${encodeURIComponent(item.email)}`);
      setMessage("Utilisateur supprime.");
      await loadData();
    } catch (err) {
      setError(getApiError(err, "Erreur suppression utilisateur."));
    }
  }

  function canDeactivate(item) {
    return item.est_actif && normalizeStatus(item) === "ACTIF" && item.id !== currentUser?.id;
  }

  function canReactivate(item) {
    return !item.est_actif && ["DESACTIVE_ADMIN", "BLOQUE_TENTATIVES"].includes(normalizeStatus(item));
  }

  return (
    <Layout
      title="Gestion utilisateurs"
      subtitle="Creer un compte, envoyer le lien d'activation et gerer les statuts."
    >
      <div className="grid grid-2">
        <div className="card">
          <h2>Creer un utilisateur</h2>

          {error && <div className="alert alert-error">{error}</div>}
          {message && <div className="alert alert-success">{message}</div>}

          {debugLink && (
            <div className="alert alert-info">
              Lien activation debug :
              <br />
              <a href={debugLink}>{debugLink}</a>
            </div>
          )}

          <form className="form" onSubmit={createUser}>
            <div className="input-group">
              <label>Email</label>
              <input
                className="input"
                type="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
                required
              />
            </div>

            <div className="input-group">
              <label>Nom complet</label>
              <input
                className="input"
                value={form.nom_complet}
                onChange={(event) => updateField("nom_complet", event.target.value)}
                required
              />
            </div>

            {isSuperAdmin ? (
              <div className="input-group">
                <label>Departement</label>
                <select
                  className="select"
                  value={form.departement_nom}
                  onChange={(event) => updateField("departement_nom", event.target.value)}
                  required
                >
                  <option value="" disabled>
                    Choisir un departement
                  </option>
                  {departements.map((item) => (
                    <option key={item.id} value={item.nom_departement}>
                      {item.nom_departement}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="input-group">
                <label>Departement</label>
                <div className="input" style={{ display: "flex", alignItems: "center" }}>
                  {currentUser?.departement_nom || "Departement associe a votre compte"}
                </div>
              </div>
            )}

            <div className="input-group">
              <label>Role</label>
              <div className="input" style={{ display: "flex", alignItems: "center" }}>
                USER
              </div>
            </div>

            <button
              className="btn btn-primary"
              disabled={loading || (isSuperAdmin && !form.departement_nom)}
            >
              <Plus size={18} />
              {loading ? "Creation..." : "Creer utilisateur"}
            </button>
          </form>
        </div>

        <div className="card">
          <h2>Resume</h2>
          <p>
            Apres creation, l'utilisateur recoit un email avec un bouton
            d'activation. Le role reste une donnee en lecture seule sur cette page.
          </p>

          {isAdmin && (
            <div className="alert alert-info">
              En tant qu'administrateur, vous gerez uniquement les utilisateurs
              de votre departement.
            </div>
          )}

          <button className="btn btn-secondary" onClick={loadData}>
            <RefreshCw size={18} />
            Actualiser
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>Liste utilisateurs</h2>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nom complet</th>
                <th>Email</th>
                <th>Role</th>
                <th>Departement</th>
                <th>Statut compte</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {users.map((item) => {
                const status = normalizeStatus(item);
                return (
                  <tr key={item.id}>
                    <td>{item.nom_complet}</td>
                    <td>{item.email}</td>
                    <td>{item.role}</td>
                    <td>
                      {isSuperAdmin ? (
                        <select
                          className="select"
                          value={item.departement_nom || ""}
                          onChange={(event) => updateUserDepartment(item, event.target.value)}
                        >
                          <option value="">Aucun departement</option>
                          {departements.map((dep) => (
                            <option key={dep.id} value={dep.nom_departement}>
                              {dep.nom_departement}
                            </option>
                          ))}
                        </select>
                      ) : (
                        item.departement_nom || "-"
                      )}
                    </td>
                    <td>
                      <span className={STATUS_CLASSES[status] || "badge badge-orange"}>
                        {STATUS_LABELS[status] || status || "Indisponible"}
                      </span>
                    </td>
                    <td>
                      <div className="actions">
                        {canDeactivate(item) && (
                          <button className="btn btn-secondary" onClick={() => toggleStatus(item)}>
                            <UserX size={16} />
                            Desactiver
                          </button>
                        )}
                        {canReactivate(item) && (
                          <button className="btn btn-secondary" onClick={() => toggleStatus(item)}>
                            <UserCheck size={16} />
                            {status === "BLOQUE_TENTATIVES" ? "Debloquer" : "Reactiver"}
                          </button>
                        )}
                        <button className="btn btn-danger" onClick={() => deleteUser(item)}>
                          <UserX size={16} />
                          Supprimer
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {users.length === 0 && (
                <tr>
                  <td colSpan="6">Aucun utilisateur.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
